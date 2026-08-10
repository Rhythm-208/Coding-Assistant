import subprocess
from State import AgentState


def git_commit(state: AgentState) -> dict:
    repo_path = state["repo_path"]
    issue_title = state.get("issue_title", "automated fix")

    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_path, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Fix: {issue_title}"],
            cwd=repo_path, check=True, capture_output=True, text=True,
        )
        return {
            "status": "done",
            "messages": [("assistant", f"Committed fix for: {issue_title}")],
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "failed",
            "messages": [("assistant", f"Commit failed:\n{e.stderr}")],
        }