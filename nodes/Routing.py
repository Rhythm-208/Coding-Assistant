from State import AgentState
import subprocess
from nodes.test import cleanup_container

def route_after_test(state: AgentState) -> str:
    result = state["test_result"]

    if result.passed:
        return "human_approval"

    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "escalate"

    return "Diagnose"



def escalate(state: AgentState) -> dict:
    # revert whatever the last apply_diff left in the working tree - we
    # never want to hand back a repo with an unproven, uncommitted patch
    # sitting in it
    repo_path = state.get("repo_path")
    if repo_path:
        subprocess.run(["git", "checkout", "--", "."], cwd=repo_path, capture_output=True)

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
