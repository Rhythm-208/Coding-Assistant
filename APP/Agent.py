from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from langchain_core.tools import tool
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
import uvicorn
import os
import uuid
from dotenv import load_dotenv

# Load env before imports that might rely on it
load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))
if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
os.environ.setdefault("LANGSMITH_TRACING", "true")

from llm import llm
from Assistant import app as assistant_workflow
from tools import write_file

# 1. Define the Tool for the conversational agent
@tool
def run_coding_workflow(message: str, repo_path: str) -> str:
    """
    Triggers the main coding assistant workflow to resolve an issue in a repository.
    Use this tool when the user asks you to fix a bug, implement a feature, or change code in a repository.
    You MUST gather the message (describing what is wrong) and repo_path from the user before calling this.
    """
    
    try:
        worflow_thread_id = str(uuid.uuid4())
        result = assistant_workflow.invoke(
            {
                "message": message,
                "repo_path": repo_path,
                "iteration": 0,
                "max_iterations": 4,
                "changes_to_make": [],
            },
            # Using a sub-thread to avoid interfering with the conversational thread
            config={"configurable": {"thread_id": worflow_thread_id}} 
        )
        status = result.get("status", "unknown")
        return f"The coding workflow has finished executing. Final status: {status}. Let the user know the task is complete."
    except Exception as e:
        return f"Error executing workflow: {str(e)}"

# 2. Set up the conversational agent
memory = MemorySaver()
chat_agent = create_agent(
    llm,
    tools=[run_coding_workflow, write_file],
    checkpointer=memory,
    system_prompt="""You are a helpful conversational AI coding assistant. You chat with the user to understand their coding problems. 
                    Once you have enough information (a single clear message describing what is wrong or what file to check, and the repository path), 
                      you should use the run_coding_workflow tool to actually fix the code. 
                          If you are missing information (like the repository path), politely ask the user for it. 
                             You can also write files if necessary."""
    
)

# 3. Set up the FastAPI server
app = FastAPI(title="Conversational Agent API")

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default-thread"

class ChatResponse(BaseModel):
    response: str

@app.post("/sessions", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        config = {"configurable": {"thread_id": request.thread_id}}
        result = chat_agent.invoke(
            {"messages": [("user", request.message)]},
            config=config
        )
        # The last message is the response from the AI
        final_message = result["messages"][-1].content
        return ChatResponse(response=final_message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("Agent:app", host="0.0.0.0", port=8000, reload=True)
