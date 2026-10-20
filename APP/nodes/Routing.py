from State import AgentState
from nodes.test import cleanup_container

def route_after_test(state: AgentState) -> str:
    result = state["test_result"]

    if result.passed:
        return "human_approval"

    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "escalate"

    return "Diagnose"



def escalate(state: AgentState) -> dict:
    # Nothing to revert on disk: patches only live in virtual_files until
    # persist_approved writes them, so the user's working tree is untouched.
    thread_id = state.get("thread_id")
    if thread_id:
        cleanup_container(thread_id)

    last_result = state.get("test_result")
    last_failure = last_result.failure_text if last_result else "(no test result recorded)"

    summary = (
        f"Escalated after {state.get('iteration', 0)} attempt(s) without a passing test.\n\n"
        f"Issue: {state.get('message', state.get('prompt', ''))}\n\n"
        f"Last diagnosis: {state.get('Diagnose')}\n\n"
        f"Last failure:\n{last_failure}"
    )

    return {
        "status": "escalated",
        "messages": [("assistant", summary)],
    }
