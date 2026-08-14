from langgraph.graph import StateGraph, START, END
import os
from dotenv import load_dotenv

from State import AgentState
from nodes.Diagnose import Diagnose
from nodes.Propose_rewrite import propose_patch
from nodes.Validate_diff import validate_diff, route_after_validation
from nodes.Apply_diff import apply_diff
from nodes.test import test_node
from nodes.HITL import human_approval
from nodes.Routing import route_after_test, route_after_approval, escalate
from nodes.commit import git_commit

# The user will need to create this node and update state (as instructed in Arc.txt)
from nodes.Propose_changes import propose_changes

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

graph = StateGraph(AgentState)

# --- Add Nodes ---
graph.add_node("Diagnose", Diagnose)
graph.add_node("propose_changes", propose_changes)
graph.add_node("propose_patch", propose_patch)
graph.add_node("validate_diff", validate_diff)
graph.add_node("apply_diff", apply_diff)
graph.add_node("test_node", test_node)
graph.add_node("human_approval", human_approval)
graph.add_node("git_commit", git_commit)
graph.add_node("escalate", escalate)

# --- Add Edges ---
graph.add_edge(START, "Diagnose")
graph.add_edge("Diagnose", "propose_changes")

graph.add_conditional_edges(
    "propose_changes",
    route_next_file,
    {"propose_patch": "propose_patch", "test_node": "test_node"}
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
    {"git_commit": "git_commit", "end": END}
)

graph.add_edge("git_commit", END)
graph.add_edge("escalate", END)

app = graph.compile()

if __name__ == "__main__":
    load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))
    if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
    os.environ.setdefault("LANGSMITH_TRACING", "true")

    # Example Invocation
    result = app.invoke(
        {
            "prompt": "Update the authentication workflow.",
            "issue_title": "Update Auth",
            "issue_description": "We need to fix the auth bypass issue.",
            "repo_url": "https://github.com/Rhythm-208/Testing.git",
            "iteration": 0,
            "max_iterations": 5,
            # We initialize changes_to_make empty, but it will be populated in propose_changes
            "changes_to_make": [], 
        }
    )
    print(result.get("status"))
    for msg in result.get("messages", []):
        print(msg)
