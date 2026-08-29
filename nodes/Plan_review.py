from State import AgentState
from langgraph.types import interrupt

def plan_review(state: AgentState) -> dict:
    if state.get("plan_review_skipped"):
        # The user requested to skip the plan review on the second pass after an edit.
        # We reset it so if a completely new plan is generated later, it can be reviewed.
        return {"plan_approval_status": "approved", "plan_review_skipped": False}

    changes = state.get("changes_to_make", [])
    
    print("\n" + "=" * 60)
    print(f"PROPOSED PLAN FOR: {state.get('message', state.get('prompt', ''))}")
    print("=" * 60)
    for c in changes:
        print(f"File: {c.get('file')}")
        print(f"Instruction: {c.get('instruction')}\n")
    print("=" * 60)
    print("Please review the plan. You can approve (proceed), reject (end pipeline), or provide feedback (edit).")

    decision = interrupt({
        "type": "plan_review",
        "changes_to_make": changes,
        "message": "Enter 'y' to approve, 'n' to reject, or type your comment/feedback to edit: "
    })
    
    if isinstance(decision, dict):
        if "feedback" in decision:
            decision_str = decision["feedback"]
            return {
                "plan_approval_status": "edit", 
                "plan_feedback": decision_str,
                "plan_review_skipped": True, # Ensure it skips next time as requested
                "messages": [("assistant", f"Human requested plan edit: {decision_str}")]
            }
        elif "changes_to_make" in decision:
            if len(decision["changes_to_make"]) > 0:
                return {"plan_approval_status": "approved", "messages": [("assistant", "Plan approved.")]}
            else:
                return {"plan_approval_status": "rejected", "status": "rejected", "messages": [("assistant", "Plan rejected by human.")]}
    
    # Fallback for string payloads (e.g. CLI usage)
    if isinstance(decision, str):
        decision = decision.strip()
    
    if isinstance(decision, str) and decision.lower() == 'y':
        return {"plan_approval_status": "approved", "messages": [("assistant", "Plan approved.")]}
    elif isinstance(decision, str) and decision.lower() == 'n':
        return {"plan_approval_status": "rejected", "status": "rejected", "messages": [("assistant", "Plan rejected by human.")]}
    else:
        # It's an edit comment
        return {
            "plan_approval_status": "edit", 
            "plan_feedback": str(decision),
            "plan_review_skipped": True, # Ensure it skips next time as requested
            "messages": [("assistant", f"Human requested plan edit: {str(decision)}")]
        }
