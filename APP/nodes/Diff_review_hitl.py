from State import AgentState
from langgraph.types import interrupt
from utils.file_persist import build_diff_payload


def diff_review_hitl(state: AgentState) -> dict:
    """
    Human-in-the-loop node that fires AFTER tests pass.

    Builds a structured per-file diff payload from virtual_files and raises a
    LangGraph interrupt so the user can review each file's changes with full
    line-number context before anything is written to disk.

    The interrupt payload shape:
        {
            "type": "diff_review",
            "files": [
                {
                    "file": "path/to/file.py",
                    "hunks": [
                        {
                            "old_start": int, "old_count": int,
                            "new_start": int, "new_count": int,
                            "lines": [{"type": "context"|"add"|"remove", "content": str}]
                        }
                    ]
                }
            ],
            "message": str
        }

    The resume payload expected from the frontend:
        {"accepted_files": ["path/a.py", ...], "declined_files": ["path/b.py", ...]}
    """
    virtual_files = state.get("virtual_files", {})
    files_payload = build_diff_payload(virtual_files)

    if not files_payload:
        # Nothing actually changed — skip review and proceed
        return {"diff_review_decision": {"accepted_files": [], "declined_files": []}}

    decision = interrupt({
        "type": "diff_review",
        "files": files_payload,
        "message": (
            f"✅ Tests passed! I've prepared changes to {len(files_payload)} file(s). "
            "Review each file and accept or decline."
        ),
    })

    # decision is the resume payload injected by Agent2._resolve_diff_review
    accepted = decision.get("accepted_files", [])
    declined = decision.get("declined_files", [])

    return {"diff_review_decision": {"accepted_files": accepted, "declined_files": declined}}
