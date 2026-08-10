from State import AgentState
from llm import propose_code_changes_agent as agent

SYSTEM_PROMPT = """You are a senior engineer implementing a requested code change.

You will be given an analysis of what needs to change and the current content of
the relevant file(s) (with line numbers for reference only).

Respond with ONLY a valid unified diff (the output of `diff -u` / `git diff`
format, using --- / +++ / @@ headers). Do NOT include any explanation,
preamble, or markdown code fences. Your entire response must be parseable
as a unified diff, nothing else.

Rules:
- The diff must apply cleanly against the exact file content shown to you.
- Do not modify any file whose path contains "test" unless the user's request 
  explicitly asks to change tests.
- If prior attempts are shown and they failed, do not repeat the same change.
- Make the minimum set of changes needed to fulfill the request.
"""


def propose_code_changes(state: AgentState) -> dict:
    """
    Generate a unified diff that implements the user's requested changes
    based on the analysis from the Analyze node.
    """

    user_prompt = f"""You are a senior software engineer implementing a code change.

USER REQUEST: {state.get('prompt')}

ANALYSIS OF WHAT TO CHANGE: {state.get('Analysis')}

REPO PATH: {state.get('repo_path')}

Use the tools to read the files that need to change, then produce a unified diff 
that implements the requested changes. Output ONLY the unified diff — no explanation,
preamble, or markdown code fences. Your entire response must be parseable 
as a unified diff, nothing else."""

    inputs = {
        "messages": [
            ("system", SYSTEM_PROMPT),
            ("user", user_prompt),
        ]
    }
    response = agent.invoke(inputs)

    return {"Propose_change": response["messages"][-1].content}
