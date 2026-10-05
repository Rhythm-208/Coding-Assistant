from State import AgentState
from utils.file_persist import apply_changes


def persist_approved(state: AgentState) -> dict:
    """
    Writes the user-approved files from virtual_files to real disk.

    Only files listed in diff_review_decision["accepted_files"] are persisted.
    Declined files are silently dropped — nothing from them touches disk.

    Returns a status of "done" if at least one file was written, "rejected"
    if the user declined everything.
    """
    decision = state.get("diff_review_decision", {})
    accepted = decision.get("accepted_files", [])
    virtual_files = state.get("virtual_files", {})

    written = []
    for filepath in accepted:
        content = virtual_files.get(filepath)
        if content is not None:
            apply_changes(filepath, content)
            written.append(filepath)

    if written:
        status = "done"
        summary = f"Applied changes to: {', '.join(written)}"
    else:
        status = "rejected"
        summary = "All proposed changes were declined — no files modified."

    return {
        "status": status,
        "messages": [("assistant", summary)],
    }
