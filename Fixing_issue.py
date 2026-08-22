from langgraph.graph import StateGraph, START, END
# LangSmith tracing is enabled via environment variables

from State import AgentState
from nodes.Initialize import initialize_workspace
from nodes.Diagnose import Diagnose
from nodes.Propose_rewrite import propose_patch
from nodes.Validate_diff import validate_diff, route_after_validation
from nodes.Apply_diff import apply_diff
from nodes.test import test_node
from nodes.HITL import human_approval
from nodes.Routing import route_after_test, route_after_approval, escalate
from nodes.commit import git_commit


graph = StateGraph(AgentState)

# --- register every node ---
graph.add_node("initialize_workspace", initialize_workspace)
graph.add_node("Diagnose", Diagnose)
graph.add_node("propose_patch", propose_patch)
graph.add_node("validate_diff", validate_diff)
graph.add_node("apply_diff", apply_diff)
graph.add_node("test_node", test_node)
graph.add_node("human_approval", human_approval)
graph.add_node("git_commit", git_commit)
graph.add_node("escalate", escalate)

# --- straight-line edges (no branching) ---
graph.add_edge(START, "initialize_workspace")
graph.add_edge("initialize_workspace", "Diagnose")
graph.add_edge("Diagnose", "propose_patch")
graph.add_edge("propose_patch", "validate_diff")
# validate_diff now has a conditional edge (Bug 5 fix)
graph.add_edge("apply_diff", "test_node")
graph.add_edge("git_commit", END)
graph.add_edge("escalate", END)

# Removed route_after_clone conditional edge

# Bug 5 fix: guard rail — only apply if validation passed
graph.add_conditional_edges(
    "validate_diff",
    route_after_validation,
    {"apply_diff": "apply_diff", "Diagnose": "Diagnose", "escalate": "escalate"},
)

graph.add_conditional_edges(
    "test_node",
    route_after_test,
    {"human_approval": "human_approval", "escalate": "escalate", "Diagnose": "Diagnose"},
)

graph.add_conditional_edges(
    "human_approval",
    route_after_approval,
    {"git_commit": "git_commit", "end": END},
)

app = graph.compile()


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    # Load environment variables from .env (project root)
    load_dotenv(dotenv_path=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")))
    # Ensure LangSmith API key is available under both variable names
    if not os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGSMITH_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
    # Enable LangSmith tracing via environment variable (already set in .env)
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    result = app.invoke(
        {
            "issue_title": "Check-dicosunt not working",
            "issue_description": "The function isnt working properly",
            "repo_path": r"C:\Users\Rhyth\Desktop\Projects\Testing",
            "file_path": "check_discount.py",
            "iteration": 0,
            "max_iterations": 5,
        }
    )
    print(result.get("status"))
    for msg in result.get("messages", []):
        print(msg)
