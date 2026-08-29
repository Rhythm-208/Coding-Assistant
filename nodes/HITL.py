import subprocess
from State import AgentState
from nodes.test import cleanup_container
from langgraph.types import interrupt


def human_approval(state: AgentState) -> dict:
    diff_text = state["validation_result"].cleaned_diff

    print("\n" + "=" * 60)
    print(f"PROPOSED FIX FOR: {state.get('message', state.get('prompt', ''))}")
    print("=" * 60)
    print(diff_text)
    print("=" * 60)
    print("This diff has already passed the test suite in the sandbox.")

    decision = interrupt({
        "type": "human_approval",
        "diff": diff_text,
        "message": "Commit this change? [y/n]: "
    })
    
    if isinstance(decision, dict):
        if decision.get("approved"):
            decision = "y"
        else:
            decision = "n"
            
    if isinstance(decision, str):
        decision = decision.strip().lower()

    thread_id = state.get("thread_id")
    if thread_id:
        cleanup_container(thread_id)  # sandbox's job is done either way, win or lose

    if decision == "y":
        return {"approved": True, "status": "done", "messages": [("assistant", "Approved - changes will be applied to your workspace.")]}

    return {
        "approved": False,
        "status": "rejected",
        "messages": [("assistant", "Change rejected by human.")],
    }
