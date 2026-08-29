from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
import os
from dotenv import load_dotenv

from State import AgentState
from nodes.Initialize import initialize_workspace
from nodes.Diagnose import Diagnose
from nodes.Propose_rewrite import propose_patch
from nodes.Validate_diff import validate_diff, route_after_validation
from nodes.Apply_diff import apply_diff
from nodes.test import test_node
from nodes.HITL import human_approval
from nodes.Routing import route_after_test, route_after_approval, escalate

# The user will need to create this node and update state (as instructed in Arc.txt)
from nodes.Propose_changes import propose_changes
from nodes.Plan_review import plan_review

def route_next_file(state: AgentState):
    """
    Checks if there are any remaining changes to make.
    If yes, routes to 'propose_patch' (which will handle the next file).
    If no, routes to 'test_node'.
    """
    changes = state.get("changes_to_make", [])
    if changes and len(changes) > 0:
        return "propose_patch"
    else:
        return "test_node"

def route_after_plan_review(state: AgentState):
    status = state.get("plan_approval_status")
    if status == "rejected":
        return "end"
    elif status == "edit":
        return "propose_changes"
    else: # "approved"
        changes = state.get("changes_to_make", [])
        if changes and len(changes) > 0:
            return "propose_patch"
        else:
            return "test_node"

graph = StateGraph(AgentState)

# --- Add Nodes ---
graph.add_node("initialize_workspace", initialize_workspace)
graph.add_node("Diagnose", Diagnose)
graph.add_node("propose_changes", propose_changes)
graph.add_node("plan_review", plan_review)
graph.add_node("propose_patch", propose_patch)
graph.add_node("validate_diff", validate_diff)
graph.add_node("apply_diff", apply_diff)
graph.add_node("test_node", test_node)
graph.add_node("human_approval", human_approval)
graph.add_node("escalate", escalate)

# --- Add Edges ---
graph.add_edge(START, "initialize_workspace")
graph.add_edge("initialize_workspace", "Diagnose")
graph.add_edge("Diagnose", "propose_changes")

graph.add_edge("propose_changes", "plan_review")

graph.add_conditional_edges(
    "plan_review",
    route_after_plan_review,
    {"propose_patch": "propose_patch", "test_node": "test_node", "end": END, "propose_changes": "propose_changes"}
)

graph.add_edge("propose_patch", "validate_diff")

graph.add_conditional_edges(
    "validate_diff",
    route_after_validation,
    {"apply_diff": "apply_diff", "Diagnose": "Diagnose", "escalate": "escalate"}
)

graph.add_conditional_edges(
    "apply_diff",
    route_next_file,
    {"propose_patch": "propose_patch", "test_node": "test_node"}
)

graph.add_conditional_edges(
    "test_node",
    route_after_test,
    {"human_approval": "human_approval", "escalate": "escalate", "Diagnose": "Diagnose"}
)

graph.add_conditional_edges(
    "human_approval",
    route_after_approval,
    {"end": END}
)

graph.add_edge("escalate", END)

memory = MemorySaver()
app = graph.compile(checkpointer=memory)

if __name__ == "__main__":
    load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))
    if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
    os.environ.setdefault("LANGSMITH_TRACING", "true")

    # Example Invocation
    result = app.invoke(
        {
            "message": "We need to fix the auth bypass issue.",
            "repo_path": r"C:\Users\Rhyth\Desktop\Projects\Testing",
            "iteration": 0,
            "max_iterations": 5,
            # We initialize changes_to_make empty, but it will be populated in propose_changes
            "changes_to_make": [], 
        },
        config={"configurable": {"thread_id": "1"}}
    )
    print(result.get("status"))
    for msg in result.get("messages", []):
        print(msg)
