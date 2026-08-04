from State import AgentState
from nodes.Clone import clone_repo
from nodes.Diagnose import Diagnose
from langgraph.graph import StateGraph,START
from nodes.Propose_rewrite import propose_patch
from nodes.Validate_diff import validate_diff
from nodes.Apply_diff import apply_diff

graph = StateGraph(AgentState)

graph.add_node("clone_repo",clone_repo)
graph.add_node("Diagnose",Diagnose)
graph.add_node("propose_patch",propose_patch)
graph.add_node("validate_diff",validate_diff)
graph.add_node("apply_diff",apply_diff)

graph.add_edge(START,"clone_repo")
graph.add_edge("clone_repo","Diagnose")
graph.add_edge("Diagnose","propose_patch")
graph.add_edge("propose_patch","validate_diff")
graph.add_edge("validate_diff","apply_diff")





