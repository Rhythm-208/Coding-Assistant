from State import AgentState
from llm import diagnose_agent as agent


def Diagnose(state: AgentState) -> AgentState:
    # Build context about previous failed attempts if any
    prev_failures = state.get("Prev_Failed_Diagnose", [])
    failure_context = ""
    if prev_failures:
        failure_context = "\n\nPREVIOUS FAILED ATTEMPTS (do NOT repeat these):\n"
        for msg in prev_failures:
            content = msg.content if hasattr(msg, "content") else str(msg)
            failure_context += f"- {content}\n"

    prompt = f"""You are a senior software developer. There is the following issue:
                 issue_title: {state["issue_title"]},
                 issue_description: {state["issue_description"]},
                 repo_path: {state.get("repo_path", "")}
                 
                 From the issue, use the tools to explore the repo structure and read 
                 the relevant files. Then give a diagnosis: what is wrong, in which files,
                 and what needs to be changed. 
                 
                 We do NOT need you to change the code — only diagnose and tell us 
                 what is wrong and in what files.{failure_context}"""
    inputs = {
        "messages": [
            ("user", prompt)
        ]
    }

    response = agent.invoke(inputs)

    final_answer = response["messages"][-1].content

    return {
        "Diagnose": final_answer,
        "Prev_Failed_Diagnose": [("assistant", f"Failed diagnosis attempt: {final_answer}")],
    }
