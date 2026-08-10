from State import AgentState
from llm import propose_rewrite_agent as agent

SYSTEM_PROMPT = """You are a senior engineer writing a code fix.

You will be given a hypothesis about a bug and the current content of
the relevant file(s) (with line numbers for reference only).

Respond with ONLY a valid unified diff (the output of `diff -u` / `git diff`
format, using --- / +++ / @@ headers). Do NOT include any explanation,
preamble, or markdown code fences. Your entire response must be parseable
as a unified diff, nothing else.

Rules:
- The diff must apply cleanly against the exact file content shown to you.
- Do not modify any file whose path contains "test".
- If prior attempts are shown and they failed, do not repeat the same change.
"""


def propose_patch(state: AgentState):

    user_prompt = f"""You are a senior software engineer. You will be given a hypothesis about a bug and the current content of
                  the relevant file.
                  Write a unified diff that fixes this.
                  TITLE: {state.get('issue_title')}
                  DESCRIPTION: {state.get('issue_description')}
                  DIAGNOSIS: {state.get('Diagnose')}
                  repo_path: {state.get('repo_path')}
                  Use the tools given to you and propose a change in unified diff only — no explanation,
preamble, or markdown code fences. Your entire response must be parseable
as a unified diff, nothing else."""

    inputs = {
        "messages": [("system", SYSTEM_PROMPT),
                     ("user", user_prompt),
                     ]
    }
    response = agent.invoke(inputs)

    return {"Propose_change": response["messages"][-1].content}
