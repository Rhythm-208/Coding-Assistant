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


def Diagnose(state: AgentState) -> AgentState:
    # Gather previous failed attempts so the LLM doesn't repeat them
    prev_failures = state.get("Prev_Failed_Diagnose", [])
    failure_context = ""
    if prev_failures:
        failure_context = "\n\nPREVIOUS FAILED ATTEMPTS (do NOT repeat these):\n"
        for msg in prev_failures:
            content = msg.content if hasattr(msg, "content") else str(msg)
            failure_context += f"- {content}\n"

    # Read the full repo into a string context
    repo_path = state.get("repo_path", "")
    repo_contents = _read_repo_files(repo_path)

    prompt = f"""You are a senior software developer. There is the following issue/request:
message: {state.get("message", state.get("prompt", ""))}
repo_path: {repo_path}

Below are ALL the files in the repository (with line numbers).
Read them carefully, then give a diagnosis: what is wrong, in which files,
and what needs to be changed.

We do NOT need you to change the code — only diagnose and tell us
what is wrong and in what files.{failure_context}

─── REPOSITORY FILES ───
{repo_contents}
"""

    # Simple LLM call — no agent / tool-calling needed
    response = llm.invoke(prompt)
    final_answer = response.content

    return {
        "Diagnose": final_answer,
        "Prev_Failed_Diagnose": [("assistant", f"Failed diagnosis attempt: {final_answer}")],
    }
