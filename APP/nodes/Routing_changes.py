from State import AgentState
import subprocess
from nodes.test import cleanup_container


def route_after_test_changes(state: AgentState) -> str:
    """Route after test for the Changes workflow — retries go to analyze_codebase."""
    result = state["test_result"]

    if result.passed:
        return "human_approval"

    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "escalate"

    return "analyze_codebase"


def route_after_validation_changes(state: AgentState) -> str:
    """Guard rail for Changes workflow — only apply if diff is valid."""
    vr = state.get("validation_result")
    if vr and vr.valid:
        return "apply_diff"

    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "escalate"
    return "analyze_codebase"


def route_after_approval_changes(state: AgentState) -> str:
    if state.get("approved"):
        return "git_commit"
    return "end"


def escalate_changes(state: AgentState) -> dict:
    """Clean up and report when the agent couldn't make the change work."""
    repo_path = state.get("repo_path")
    if repo_path:
        subprocess.run(["git", "checkout", "--", "."], cwd=repo_path, capture_output=True)

    thread_id = state.get("thread_id")
    if thread_id:
        cleanup_container(thread_id)

    last_result = state.get("test_result")
    last_failure = last_result.failure_text if last_result else "(no test result recorded)"

    summary = (
        f"Escalated after {state.get('iteration', 0)} attempt(s) without passing tests.\n\n"
        f"User request: {state.get('prompt')}\n\n"
        f"Last analysis: {state.get('Analysis')}\n\n"
        f"Last failure:\n{last_failure}"
    )

    return {
        "status": "escalated",
        "messages": [("assistant", summary)],
    }
