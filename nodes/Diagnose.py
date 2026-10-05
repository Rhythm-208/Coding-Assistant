from pathlib import Path
from State import AgentState
from llm import llm


def _read_repo_files(repo_path: str, max_file_size: int = 50_000) -> str:
    """Walk the repo and return every readable text file with numbered lines.

    Skips hidden dirs (.git, .venv, __pycache__, node_modules) and binary /
    oversized files so the context stays manageable.
    """
    skip_dirs = {".git", ".venv", "__pycache__", "node_modules", ".idea", ".vs"}
    root = Path(repo_path)
    if not root.exists():
        return f"[ERROR] repo_path does not exist: {repo_path}"

    parts: list[str] = []
    for file in sorted(root.rglob("*")):
        # skip hidden / junk directories
        if any(part in skip_dirs for part in file.parts):
            continue
        if not file.is_file():
            continue
        # skip large / binary files
        if file.stat().st_size > max_file_size:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel = file.relative_to(root)
        numbered = "\n".join(
            f"{i + 1}: {line}" for i, line in enumerate(text.splitlines())
        )
        parts.append(f"── {rel} ──\n{numbered}")

    if not parts:
        return "[WARNING] No readable files found in the repository."

    return "\n\n".join(parts)


from pydantic import BaseModel, Field
from typing import List

class FileChange(BaseModel):
    file: str = Field(description="Absolute path to the file to change or create")
    instruction: str = Field(description="Specific instruction for what to change or create in the file")
    action: str = Field(default="edit", description="'create' for a brand-new file that does not exist yet, 'edit' to modify an existing file")

class DiagnoseAndPlan(BaseModel):
    diagnosis: str = Field(description="What is wrong, in which files, and what needs to be changed.")
    changes_to_make: List[FileChange]
    file_path: str = Field(description="The absolute path of a single file in the repository that should be executed to verify the code runs without errors.")


def Diagnose(state: AgentState) -> dict:
    # Gather previous failed attempts so the LLM doesn't repeat them
    prev_failures = state.get("Prev_Failed_Diagnose", [])
    failure_context = ""
    if prev_failures:
        failure_context = "\n\nPREVIOUS FAILED ATTEMPTS (do NOT repeat these):\n"
        for msg in prev_failures:
            content = msg.content if hasattr(msg, "content") else str(msg)
            failure_context += f"- {content}\n"

    plan_feedback = state.get('plan_feedback')
    feedback_section = f"\nPREVIOUS PLAN FEEDBACK:\nThe user reviewed your previous plan and provided the following feedback/edit request: {plan_feedback}\nPlease incorporate this feedback into your new plan.\n" if plan_feedback else ""

    # Read the full repo into a string context — cached across retries
    repo_path = state.get("repo_path", "")
    repo_contents = state.get("repo_contents")
    if not repo_contents:
        repo_contents = _read_repo_files(repo_path)

    prompt = f"""You are a senior software developer. There is the following issue/request:
message: {state.get("message", state.get("prompt", ""))}
repo_path: {repo_path}
{feedback_section}

Below are ALL the files in the repository (with line numbers).
Read them carefully, then:
1. Diagnose what is wrong, in which files, and what needs to be changed.
2. Determine the list of files that need to be changed, and a specific instruction for what to change in each file.
3. Provide the absolute path of a single file in the repository that can be run (e.g., the main entrypoint or a relevant script) to check if the changes successfully run without errors.

If the fix requires creating a new file that does not exist yet, set action to "create" for that entry.
If modifying an existing file, set action to "edit" (the default).
{failure_context}

─── REPOSITORY FILES ───
{repo_contents}
"""

    structured_llm = llm.with_structured_output(DiagnoseAndPlan)
    response = structured_llm.invoke(prompt)

    if response:
        changes = [change.model_dump() for change in response.changes_to_make]
        file_path = response.file_path
        final_answer = response.diagnosis
    else:
        changes = []
        file_path = ""
        final_answer = "Failed to generate diagnosis."

    return {
        "Diagnose": final_answer,
        "repo_contents": repo_contents,  # cache for subsequent retries
        "Prev_Failed_Diagnose": [("assistant", f"Failed diagnosis attempt: {final_answer}")],
        "changes_to_make": changes,
        "file_path": file_path
    }

