import os
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_core.tools import tool
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
import uvicorn
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))
if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
os.environ.setdefault("LANGSMITH_TRACING", "true")

from llm import llm
from Assistant import app as assistant_workflow
from tools import write_file


# ---------------------------------------------------------------------
# Pending-interrupt tracking, keyed by the CHAT thread_id (not the
# workflow's own thread_id). When a workflow run pauses, we remember
# which workflow thread it paused on, so the NEXT chat message can be
# routed straight to resuming it instead of going through the LLM again.
# ---------------------------------------------------------------------
pending_interrupts: dict[str, dict] = {}
# shape: { chat_thread_id: {"workflow_thread_id": str, "interrupt_type": str, "raw": dict} }

_agent_cache: dict[str, object] = {}   # chat_thread_id -> compiled chat agent
memory = MemorySaver()


def _extract_interrupt(result: dict):
    if "__interrupt__" in result:
        return result["__interrupt__"][0].value
    return None


def _run_workflow(workflow_thread_id: str, input_data) -> dict:
    config = {"configurable": {"thread_id": workflow_thread_id}}
    result = assistant_workflow.invoke(input_data, config)
    interrupt = _extract_interrupt(result)
    if interrupt:
        return {"paused": True, "interrupt": interrupt}
    return {"paused": False, "status": result.get("status"), "messages": result.get("messages", [])}


def _describe_interrupt_for_chat(interrupt: dict) -> str:
    if interrupt["type"] == "plan_review":
        files = ", ".join(c["file_path"] for c in interrupt["changes_to_make"])
        return (
            f"Here's my proposed plan - I'd touch: {files}.\n\n"
            f"Reply 'y' to proceed, 'n' to cancel, or tell me what to change about the plan."
        )
    if interrupt["type"] == "human_approval":
        return (
            f"The fix passed all tests. Here's the diff:\n\n{interrupt['diff']}\n\n"
            f"Reply 'y' to commit it, 'n' to discard it."
        )
    return f"Workflow paused: {interrupt}"


def _build_chat_agent(chat_thread_id: str):
    """
    chat_thread_id is captured via closure here, NOT passed as a tool
    argument the LLM has to remember/echo back. This avoids relying on
    the model correctly relaying an internal id it has no real reason
    to track - same reasoning as interactive_tools.py's
    make_tools(project_root) pattern.
    """

    @tool
    def run_coding_workflow(prompt: str, issue_title: str, issue_description: str, repo_path: str) -> str:
        """
        Starts the coding workflow to resolve an issue in a repository.
        Use this once you've gathered a clear description of the problem
        AND the repository path from the user in conversation.
        """
        workflow_thread_id = str(uuid.uuid4())   # fresh every run - never reused

        try:
            outcome = _run_workflow(workflow_thread_id, {
                "prompt": prompt,
                "issue_title": issue_title,
                "issue_description": issue_description,
                "repo_path": repo_path,
                "thread_id": workflow_thread_id,   # also test_node's Docker sandbox key
                "iteration": 0,
                "max_iterations": 4,
                "changes_to_make": [],
            })
        except Exception as e:
            return f"Error starting workflow: {str(e)}"

        if outcome["paused"]:
            pending_interrupts[chat_thread_id] = {
                "workflow_thread_id": workflow_thread_id,
                "interrupt_type": outcome["interrupt"]["type"],
                "raw": outcome["interrupt"],
            }
            return _describe_interrupt_for_chat(outcome["interrupt"])

        return f"Workflow finished. Status: {outcome['status']}."

    return create_agent(
        llm,
        tools=[run_coding_workflow, write_file],
        checkpointer=memory,
        system_prompt="""You are a helpful conversational AI coding assistant.
Chat with the user to understand their coding problem. You MUST ask for
the repository path if the user hasn't given it, before calling
run_coding_workflow - never guess or assume a path.
Once you have a clear description of the problem and the repo path,
call run_coding_workflow.""",
    )


def _get_chat_agent(chat_thread_id: str):
    if chat_thread_id not in _agent_cache:
        _agent_cache[chat_thread_id] = _build_chat_agent(chat_thread_id)
    return _agent_cache[chat_thread_id]


app = FastAPI(title="Conversational Agent API")


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default-thread"


class ChatResponse(BaseModel):
    response: str


def _resolve_reply_to_payload(interrupt_type: str, message: str, raw_interrupt: dict) -> Optional[dict]:
    """Turns a plain-text chat reply into the dict resume() expects."""
    text = message.strip().lower()

    if interrupt_type == "human_approval":
        if text in ("y", "yes"):
            return {"approved": True}
        if text in ("n", "no"):
            return {"approved": False}
        # TODO: workflow.py's route_after_approval only routes to
        # "git_commit" or END - there's no wired path back to Diagnose
        # for feedback on an already-tested diff yet. Until that edge
        # exists, feedback here is treated as a reject and the comment
        # itself isn't acted on by the graph.
        return {"approved": False, "feedback": message}

    if interrupt_type == "plan_review":
        if text in ("y", "yes"):
            return {"changes_to_make": raw_interrupt["changes_to_make"]}
        if text in ("n", "no"):
            return {"changes_to_make": []}
        # plan_review needs updating to handle a "feedback" key by
        # looping back to propose_changes - see nodes/Plan_review.py
        return {"feedback": message}

    return None


@app.post("/sessions", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        pending = pending_interrupts.get(request.thread_id)

        if pending:
            payload = _resolve_reply_to_payload(pending["interrupt_type"], request.message, pending["raw"])
            outcome = _run_workflow(pending["workflow_thread_id"], Command(resume=payload))

            if outcome["paused"]:
                pending_interrupts[request.thread_id] = {
                    "workflow_thread_id": pending["workflow_thread_id"],
                    "interrupt_type": outcome["interrupt"]["type"],
                    "raw": outcome["interrupt"],
                }
                return ChatResponse(response=_describe_interrupt_for_chat(outcome["interrupt"]))

            del pending_interrupts[request.thread_id]
            return ChatResponse(response=f"Workflow finished. Status: {outcome['status']}.")

        # no pending interrupt - normal conversational turn
        agent = _get_chat_agent(request.thread_id)
        config = {"configurable": {"thread_id": request.thread_id}}
        result = agent.invoke({"messages": [("user", request.message)]}, config=config)
        return ChatResponse(response=result["messages"][-1].content)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("Agent:app", host="0.0.0.0", port=8000, reload=True)