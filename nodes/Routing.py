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


def route_after_approval(state: AgentState) -> str:
    """
    Runs after human_approval. That node already did the real work for
    the rejection path (reverted the working tree, set status="rejected"),
    so this function only needs to decide where to route next:
      - approved -> git_commit actually performs the commit
      - rejected -> nothing left to do, go straight to END
    """
    if state.get("approved"):
        return "git_commit"
    return "end"


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
        f"Issue: {state.get('issue_title')}\n\n"
        f"Last diagnosis: {state.get('Diagnose')}\n\n"
        f"Last failure:\n{last_failure}"
    )

    return {
        "status": "escalated",
        "messages": [("assistant", summary)],
    }
