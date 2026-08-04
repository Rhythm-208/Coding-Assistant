import subprocess
from ..State import AgentState , ApplyResult
from dataclasses import dataclass
from pathlib import Path




def apply_diff(state:AgentState):
    repo  =  Path(state['repo_path'])
    diff_text = state['validation_result']['cleaned_diff']

    if not repo.is_dir():
        raise FileNotFoundError(f"repo_path does not exist: {state['repo_path']}")

    if not diff_text.endswith("\n"):
        diff_text += "\n"

    check = subprocess.run(
        ["git", "apply", "--check", "-"],
        input=diff_text,
        cwd=str(repo),
        text=True,
        capture_output=True,
    )
    if check.returncode != 0:
        return {'apply_diff':ApplyResult(
            success=False,
            error_message=f"Dry-run check failed, diff would not apply cleanly:\n{check.stderr}",
        )}

    apply = subprocess.run(
        ["git", "apply", "-"],
        input=diff_text,
        cwd=str(repo),
        text=True,
        capture_output=True,
    )
    if apply.returncode != 0:
        # should be rare since --check already passed, but handle it anyway
        return {'apply_diff': ApplyResult(
            success=False,
            error_message=f"Apply failed even after dry-run passed:\n{apply.stderr}",
        )}

    return {'apply_diff': ApplyResult(success=True)}





