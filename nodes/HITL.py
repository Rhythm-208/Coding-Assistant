import subprocess
from State import AgentState
from nodes.test import cleanup_container


def _commit_changes(repo_path: str, issue_title: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"Fix: {issue_title}"],
        cwd=repo_path, check=True, capture_output=True,
    )


def _revert_changes(repo_path: str) -> None:
    subprocess.run(["git", "checkout", "--", "."], cwd=repo_path, capture_output=True)


def human_approval(state: AgentState) -> dict:
    repo_path = state["repo_path"]
    diff_text = state["validation_result"].cleaned_diff

    print("\n" + "=" * 60)
    print(f"PROPOSED FIX FOR: {state.get('issue_title')}")
    print("=" * 60)
    print(diff_text)
    print("=" * 60)
    print("This diff has already passed the test suite in the sandbox.")

    decision = input("Commit this change? [y/n]: ").strip().lower()

    thread_id = state.get("thread_id")
    if thread_id:
        cleanup_container(thread_id)  # sandbox's job is done either way

    if decision == "y":
        try:
            _commit_changes(repo_path, state.get("issue_title", "automated fix"))
            return {"status": "done", "messages": [("assistant", "Change approved and committed.")]}
        except subprocess.CalledProcessError as e:
            return {"status": "failed", "messages": [("assistant", f"Commit failed: {e.stderr}")]}

    _revert_changes(repo_path)
    return {"status": "rejected", "messages": [("assistant", "Change rejected by human, reverted.")]}
