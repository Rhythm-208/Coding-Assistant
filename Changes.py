from langgraph.graph import StateGraph, START, END

from State import AgentState
from nodes.Clone import clone_repo, route_after_clone
from nodes.Analyze import analyze_codebase
from nodes.Propose_code_changes import propose_code_changes
from nodes.Validate_diff import validate_diff
from nodes.Apply_diff import apply_diff
from nodes.test import test_node
from nodes.HITL import human_approval
from nodes.Routing_changes import (
    route_after_test_changes,
    route_after_validation_changes,
    route_after_approval_changes,
    escalate_changes,
)
from nodes.commit import git_commit


graph = StateGraph(AgentState)

# --- register every node ---
graph.add_node("clone_repo", clone_repo)
graph.add_node("analyze_codebase", analyze_codebase)
graph.add_node("propose_code_changes", propose_code_changes)
graph.add_node("validate_diff", validate_diff)
graph.add_node("apply_diff", apply_diff)
graph.add_node("test_node", test_node)
graph.add_node("human_approval", human_approval)
graph.add_node("git_commit", git_commit)
graph.add_node("escalate", escalate_changes)

# --- straight-line edges ---
graph.add_edge(START, "clone_repo")
graph.add_edge("analyze_codebase", "propose_code_changes")
graph.add_edge("propose_code_changes", "validate_diff")
graph.add_edge("apply_diff", "test_node")
graph.add_edge("git_commit", END)
graph.add_edge("escalate", END)

# --- branching edges ---
graph.add_conditional_edges(
    "clone_repo",
    route_after_clone,
    # route_after_clone returns "Diagnose" on success, but we map it to analyze_codebase
    {"Diagnose": "analyze_codebase", "escalate": "escalate"},
)

graph.add_conditional_edges(
    "validate_diff",
    route_after_validation_changes,
    {"apply_diff": "apply_diff", "analyze_codebase": "analyze_codebase", "escalate": "escalate"},
)

graph.add_conditional_edges(
    "test_node",
    route_after_test_changes,
    {"human_approval": "human_approval", "escalate": "escalate", "analyze_codebase": "analyze_codebase"},
)

graph.add_conditional_edges(
    "human_approval",
    route_after_approval_changes,
    {"git_commit": "git_commit", "end": END},
)

changes_app = graph.compile()


if __name__ == "__main__":
    result = changes_app.invoke({
        "prompt": "Add a /health endpoint that returns {'status': 'ok'} as JSON",
        "repo_url": "https://github.com/example/example.git",
        "iteration": 0,
        "max_iterations": 5,
    })
    print(result.get("status"))
    for msg in result.get("messages", []):
        print(msg)
