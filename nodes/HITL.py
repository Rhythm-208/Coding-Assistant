import subprocess
from State import AgentState
from nodes.test import cleanup_container


def _revert_changes(repo_path: str) -> None:
    subprocess.run(["git", "checkout", "--", "."], cwd=repo_path, capture_output=True)


def human_approval(state: AgentState) -> dict:
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
        cleanup_container(thread_id)  # sandbox's job is done either way, win or lose

    if decision == "y":
        return {"approved": True, "messages": [("assistant", "Approved - committing now.")]}

    _revert_changes(state["repo_path"])
    return {
        "approved": False,
        "status": "rejected",
        "messages": [("assistant", "Change rejected by human, reverted.")],
    }
