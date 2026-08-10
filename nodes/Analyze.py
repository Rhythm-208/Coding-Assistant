from State import AgentState
from llm import analyze_agent as agent


def analyze_codebase(state: AgentState) -> dict:
    """
    Understand the codebase and figure out exactly what needs to change
    to fulfill the user's prompt. This is the 'planning' step — no code
    changes happen here, only analysis.
    """
    prev_failures = state.get("Prev_Failed_Diagnose", [])
    failure_context = ""
    if prev_failures:
        failure_context = "\n\nPREVIOUS FAILED ATTEMPTS (do NOT repeat these approaches):\n"
        for msg in prev_failures:
            content = msg.content if hasattr(msg, "content") else str(msg)
            failure_context += f"- {content}\n"

    prompt = f"""You are a senior software engineer. A user has requested the following change 
to a codebase:

USER REQUEST: {state["prompt"]}

The repo is cloned at: {state.get("repo_path", "")}

Your job:
1. Use the tools to explore the repo structure (list folders, read files).
2. Understand the current architecture and code.
3. Identify EXACTLY which files need to be modified and what changes are needed.
4. Produce a detailed analysis — which files, which functions/classes, what to add/remove/modify.

Do NOT write any code or diffs. Only produce an analysis of what needs to change 
and where.{failure_context}"""

    inputs = {
        "messages": [("user", prompt)]
    }

    response = agent.invoke(inputs)
    final_answer = response["messages"][-1].content

    return {
        "Analysis": final_answer,
        "Prev_Failed_Diagnose": [("assistant", f"Failed analysis attempt: {final_answer}")],
    }
