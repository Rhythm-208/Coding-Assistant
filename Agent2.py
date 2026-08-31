import os
import uuid
from typing import Optional
 
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.tools import tool
from langchain.agents import create_agent
from langsmith import traceable
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import uvicorn
from dotenv import load_dotenv
 
load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))
if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
os.environ.setdefault("LANGSMITH_TRACING", "true")
 
from llm import chat_llm
from Assistant import app as assistant_workflow
 
 
# ── In-memory state stores ────────────────────────────────────────────
pending_interrupts: dict[str, dict] = {}
# shape: { chat_thread_id: {"workflow_thread_id": str, "interrupt_type": str, "raw": dict} }
 
_agent_cache: dict[str, object] = {}        # chat_thread_id -> compiled chat agent (built once, reused)
_session_repo_paths: dict[str, str] = {}    # chat_thread_id -> repo_path, OVERWRITTEN on every request
memory = InMemorySaver()
 
 
# ── Interrupt helpers ─────────────────────────────────────────────────
 
def _extract_interrupt(result: dict):
    if "__interrupt__" not in result:

        return None

    raw = result["__interrupt__"][0].value

    if isinstance(raw, dict):
        return raw if "type" in raw else {**raw, "type": raw.get("type", "generic")}

    return {"type": "generic", "message": str(raw)}

 
@traceable(name="assistant_workflow_run", run_type="chain")
def _run_workflow(workflow_thread_id: str, input_data) -> dict:
    """
    Invokes the Assistant.py LangGraph workflow (which uses the local LLM).
    Detects interrupts and returns them in a normalised shape.
    LangSmith traces this as a child run under the parent chat turn.
    """
    config = {"configurable": {"thread_id": workflow_thread_id}}
    result = assistant_workflow.invoke(input_data, config)
    interrupt = _extract_interrupt(result)
    if interrupt:
        return {"paused": True, "interrupt": interrupt}
    return {"paused": False, "status": result.get("status"), "messages": result.get("messages", [])}
 
 
# ── HITL interrupt registry ────────────────────────────────────────────
#
# Assistant.py can call interrupt() at any number of checkpoints (plan
# review, diff approval, clarification requests, test-failure retries,
# per-file confirmation, etc). Every checkpoint needs two things:
#   1. a "describe" function  -> turns the raw interrupt payload into a
#      human-readable chat message
#   2. a "resolve" function   -> turns the user's plain-text chat reply
#      back into the structured payload Command(resume=...) expects
#
# Register a new entry here every time Assistant.py adds an interrupt()
# call with a new `type`. Anything NOT registered falls back to the
# generic handlers below instead of crashing or resuming with None.
 
def _describe_plan_review(interrupt: dict) -> str:
    changes = interrupt.get("changes_to_make", [])
    if not changes:
        return "Here is my proposed plan — I have no files to change.\n\nReply 'y' to proceed anyway, 'n' to cancel, or tell me what to change about the plan."
    
    plan_text = "Here's my proposed plan:\n\n"
    for c in changes:
        file_path = c.get("file", c.get("file_path", "unknown file"))
        instruction = c.get("instruction", "No specific instruction provided.")
        plan_text += f"• **{file_path}**: {instruction}\n"
        
    plan_text += "\nReply 'y' to proceed, 'n' to cancel, or tell me what to change about the plan."
    return plan_text
 
 
def _resolve_plan_review(message: str, raw: dict) -> dict:
    text = message.strip().lower()
    if text in ("y", "yes"):
        return {"changes_to_make": raw["changes_to_make"]}
    if text in ("n", "no"):
        return {"changes_to_make": []}
    return {"feedback": message}
 
 
def _describe_human_approval(interrupt: dict) -> str:
    return (
        f"The fix passed all tests. Here's the diff:\n\n{interrupt.get('diff', '')}\n\n"
        f"Reply 'y' to apply it to your workspace, 'n' to discard it."
    )
 
 
def _resolve_human_approval(message: str, raw: dict) -> dict:
    text = message.strip().lower()
    if text in ("y", "yes"):
        return {"approved": True}
    if text in ("n", "no"):
        return {"approved": False}
    return {"approved": False, "feedback": message}
 
 
def _describe_generic(interrupt: dict) -> str:
    """
    Fallback for any interrupt type that hasn't been registered yet.
    Keeps the chat usable instead of printing a raw dict or crashing,
    so a new interrupt() call in Assistant.py degrades gracefully
    until you add a proper handler for it above.
    """
    prompt = (
        interrupt.get("message")
        or interrupt.get("question")
        or interrupt.get("prompt")
        or f"The assistant paused ({interrupt.get('type', 'unknown')}) and needs your input to continue."
    )
    return f"{prompt}\n\n(Reply 'y'/'n' for a yes-or-no confirmation, or type your answer.)"
 
 
def _resolve_generic(message: str, raw: dict) -> dict:
    text = message.strip().lower()
    if text in ("y", "yes"):
        return {"approved": True, "response": message}
    if text in ("n", "no"):
        return {"approved": False, "response": message}
    return {"response": message}
 
 
INTERRUPT_HANDLERS: dict[str, dict] = {
    "plan_review": {"describe": _describe_plan_review, "resolve": _resolve_plan_review},
    "human_approval": {"describe": _describe_human_approval, "resolve": _resolve_human_approval},
    # Add one line per new Assistant.py interrupt type, e.g.:
    # "test_failure_review": {"describe": _describe_test_failure_review, "resolve": _resolve_test_failure_review},
    # "clarification_needed": {"describe": _describe_clarification, "resolve": _resolve_clarification},
}
 
 
def _describe_interrupt_for_chat(interrupt: dict) -> str:
    handler = INTERRUPT_HANDLERS.get(interrupt.get("type"))
    if handler:
        return handler["describe"](interrupt)
    return _describe_generic(interrupt)
 
 
def _resolve_reply_to_payload(interrupt_type: str, message: str, raw_interrupt: dict) -> Optional[dict]:
    handler = INTERRUPT_HANDLERS.get(interrupt_type)
    if handler:
        return handler["resolve"](message, raw_interrupt)
    return _resolve_generic(message, raw_interrupt)
 
 
# ── Chat agent factory ────────────────────────────────────────────────
 
def _build_chat_agent(chat_thread_id: str):
    """
    Built ONCE per chat_thread_id and cached.
 
    The agent uses gemini-2.5-flash (chat_llm) via create_agent and has
    exactly one tool:
      • run_assistant – delegate a coding task to the Assistant.py workflow
                        (which internally uses the local LLM)
 
    repo_path is intentionally NOT baked into the closure at build time.
    It is read from _session_repo_paths[chat_thread_id] fresh on every
    run_assistant call, so a later request that updates the path takes effect.
    """
 
    @tool
    @traceable(name="tool_run_assistant", run_type="tool")
    def run_assistant(instruction: str) -> str:
        """
        Delegate a coding task to the assistant workflow.
        Provide a clear, self-contained description of what needs to be done
        (e.g. the bug to fix, the feature to add, or the refactor required).
 
        The assistant will:
          1. Diagnose the issue
          2. Propose a plan (pauses for human plan review)
          3. Write and validate patches
          4. Run tests in a sandbox
          5. Surface the final diff for human approval (HITL)
 
        You do NOT need to provide the repository path — it is already known.
        After calling this tool, relay the returned message to the user.
        """
        repo_path = _session_repo_paths.get(chat_thread_id)
        if not repo_path:
            return "Error: no repo_path is known for this session yet."
 
        workflow_thread_id = str(uuid.uuid4())   # fresh every run — never reused
 
        try:
            outcome = _run_workflow(workflow_thread_id, {
                "message": instruction,
                "repo_path": repo_path,
                "thread_id": workflow_thread_id,
                "iteration": 0,
                "max_iterations": 4,
                "changes_to_make": [],
            })
        except Exception as e:
            return f"Error starting assistant workflow: {str(e)}"
 
        if outcome["paused"]:
            pending_interrupts[chat_thread_id] = {
                "workflow_thread_id": workflow_thread_id,
                "interrupt_type": outcome["interrupt"]["type"],
                "raw": outcome["interrupt"],
            }
            return _describe_interrupt_for_chat(outcome["interrupt"])
 
        return f"Assistant workflow finished. Status: {outcome['status']}."
 
    return create_agent(
        chat_llm,
        tools=[run_assistant],
        checkpointer=memory,
       
        system_prompt="""You are a proactive AI coding assistant. \
The repository you are working in is already loaded — do NOT ask the user for a path.
 
You have one tool:
  • run_assistant — delegate a coding/bug-fix task to the assistant workflow
 
Workflow:
1. If the user asks you to CHANGE, WRITE, or FIX any code, you MUST use the run_assistant tool.
   Do NOT attempt to provide the code fix directly in your text response. You must delegate any file modifications to the run_assistant.
2. run_assistant may return a message asking the user to approve a plan or a diff.
   Relay that message naturally to the user and wait for their reply.
3. When the user replies 'y'/'n' or provides feedback on a plan or diff,
   the system handles resuming the workflow automatically — just acknowledge.
 
CRITICAL:
  - Use the official tool-calling API to invoke tools.
  - Do NOT output raw JSON blocks in your text response — they will not be executed.
  - Never modify files directly — all file changes MUST go through run_assistant.
""",
    )
 
 
def _get_chat_agent(chat_thread_id: str):
    if chat_thread_id not in _agent_cache:
        _agent_cache[chat_thread_id] = _build_chat_agent(chat_thread_id)
    return _agent_cache[chat_thread_id]
 
 
# ── FastAPI app ───────────────────────────────────────────────────────
 
app = FastAPI(title="Conversational Agent API")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
 
 
class ChatRequest(BaseModel):
    message: str
    thread_id: str
    repo_path: str   # required every request — no default, no Optional
 
 
class ChatResponse(BaseModel):
    response: str
 
 
@app.post("/sessions", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main chat endpoint consumed by the VS Code ChatViewProvider.
 
    Accepts: { message, thread_id, repo_path }
    Returns: { response }
 
    Flow:
      A) If a workflow interrupt is pending for this thread, resolve it
         by resuming the workflow with the user's reply — no LLM call needed.
         Any number of interrupt types is supported via INTERRUPT_HANDLERS,
         including several DIFFERENT interrupts back-to-back within the
         same run_assistant call (plan review -> ... -> diff approval -> ...).
      B) Otherwise, invoke the gemini-2.5-flash chat agent which may call
         read_file, list_files, or run_assistant (which internally uses
         the local LLM and can itself trigger an interrupt).
    """
    try:
        # Always keep the repo_path fresh for this session
        _session_repo_paths[request.thread_id] = request.repo_path
        pending = pending_interrupts.get(request.thread_id)
 
        # ── Path A: resume a paused workflow ──────────────────────────
        if pending:
            @traceable(
                name="workflow_resume",
                run_type="chain",
                metadata={"thread_id": request.thread_id, "interrupt_type": pending["interrupt_type"]},
            )
            def _resume_workflow(message: str) -> dict:
                payload = _resolve_reply_to_payload(
                    pending["interrupt_type"], message, pending["raw"]
                )
                return _run_workflow(pending["workflow_thread_id"], Command(resume=payload))
 
            outcome = _resume_workflow(request.message)
 
            if outcome["paused"]:
                # Another interrupt from the same workflow run — could be a
                # DIFFERENT type than the one just resolved. Handled generically.
                pending_interrupts[request.thread_id] = {
                    "workflow_thread_id": pending["workflow_thread_id"],
                    "interrupt_type": outcome["interrupt"]["type"],
                    "raw": outcome["interrupt"],
                }
                return ChatResponse(response=_describe_interrupt_for_chat(outcome["interrupt"]))
 
            # Workflow completed
            del pending_interrupts[request.thread_id]
            return ChatResponse(response=f"Done! Status: {outcome['status']}.")
 
        # ── Path B: normal chat turn via gemini-2.5-flash agent ───────
        @traceable(
            name="chat_turn",
            run_type="chain",
            metadata={"thread_id": request.thread_id, "repo_path": request.repo_path},
        )
        def _invoke_chat_agent(message: str) -> str:
            agent = _get_chat_agent(request.thread_id)
            config = {
                "configurable": {"thread_id": request.thread_id},
                "metadata": {
                    "thread_id": request.thread_id,
                    "repo_path": request.repo_path,
                },
            }
            result = agent.invoke({"messages": [("user", message)]}, config=config)
            content = result["messages"][-1].content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        parts.append(block)
                return "\n".join(parts)
            return str(content)
 
        response_text = _invoke_chat_agent(request.message)
        return ChatResponse(response=response_text)
 
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
 
 
if __name__ == "__main__":
    uvicorn.run("Agent2:app", host="0.0.0.0", port=8000, reload=True)
 