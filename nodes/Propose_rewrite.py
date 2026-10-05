from State import AgentState
from llm import propose_rewrite_llm
from pathlib import Path

from nodes.Patch_schema import ProposedPatch
from langsmith import traceable

SYSTEM_PROMPT = """You are a senior engineer proposing a code fix.

Respond ONLY through the structured output schema you've been given - do
not write any prose, explanation, or markdown fences, the schema is your
entire response.

For EDITING an existing file:
- `search` must be the EXACT existing code, copied verbatim (including
  whitespace and indentation) from the file content you were shown.
- Keep `search` as SHORT as possible while still being unique in the
  file - a few lines, not an entire function, unless the whole function
  is actually changing.
- `replace` is the new code that should take its place.

For CREATING a brand new file:
- Leave `search` empty.
- Put the complete file content in `replace`.

Rules:
- Never touch any file whose path contains "test".
- If prior failed attempts are shown, do not repeat the same change -
  address why it failed.
- You may include multiple blocks, across multiple files, in one response.
"""


def _read_file_content(file_path: str, virtual_files: dict) -> str:
    """Read file content from virtual_files first, then fall back to disk."""
    content = virtual_files.get(file_path)
    if content is not None:
        return content
    try:
        return Path(file_path).read_text()
    except Exception as e:
        return f"[ERROR] Could not read {file_path}: {e}"


def _invoke_structured(user_prompt: str) -> ProposedPatch:
    structured_llm = propose_rewrite_llm.with_structured_output(ProposedPatch)
    return structured_llm.invoke([
        ("system", SYSTEM_PROMPT),
        ("user", user_prompt),
    ])


@traceable(name="propose_patch")
def propose_patch(state: AgentState) -> dict:
    changes = state.get("changes_to_make", [])
    current_change = changes[0] if changes else None
    virtual_files = state.get("virtual_files", {})

    if current_change:
        file_to_edit = current_change.get("file", "")
        instruction = current_change.get("instruction", "")
        action = current_change.get("action", "edit")

        if action == "create":
            user_prompt = f"""MESSAGE: {state.get('message', state.get('prompt', ''))}
DIAGNOSIS: {state.get('Diagnose')}
REPO_PATH: {state.get('repo_path')}

CURRENT TASK: Create a new file: {file_to_edit}
INSTRUCTION: {instruction}

Produce one block for this file, with an empty search field and the
complete file content in replace."""
        else:
            file_content = _read_file_content(file_to_edit, virtual_files)
            user_prompt = f"""MESSAGE: {state.get('message', state.get('prompt', ''))}
DIAGNOSIS: {state.get('Diagnose')}
REPO_PATH: {state.get('repo_path')}

CURRENT TASK: Modify the file: {file_to_edit}
INSTRUCTION: {instruction}

CURRENT FILE CONTENTS of {file_to_edit}:
{file_content}"""

        patch = _invoke_structured(user_prompt)
        return {"Propose_change": patch, "current_change": current_change}

    # fallback - old workflow, no changes_to_make plan available
    repo_contents = state.get("repo_contents", "")
    if not repo_contents:
        from nodes.Diagnose import _read_repo_files
        repo_contents = _read_repo_files(state.get("repo_path", ""))

    user_prompt = f"""MESSAGE: {state.get('message', state.get('prompt', ''))}
DIAGNOSIS: {state.get('Diagnose')}
REPO_PATH: {state.get('repo_path')}

Below are the repository files. Based on the diagnosis, propose the
needed changes.

─── REPOSITORY FILES ───
{repo_contents}"""

    patch = _invoke_structured(user_prompt)
    return {"Propose_change": patch}