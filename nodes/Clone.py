import subprocess
import tempfile
import uuid
from State import AgentState, CloneResult


#Point to keep to check:
def route_after_clone(state: AgentState) -> str:
    if not state["clone_result"].success:
        return "escalate"       # or "failed", whatever you name your end/error node
    return "Diagnose"

def clone_repo(state:AgentState):
    """
    Clones repo_url into a fresh temp directory. Never touches an
    existing folder - always creates its own, so there's no risk of
    cloning into something that already has unrelated files in it.
    """
    dest_dir = tempfile.mkdtemp(prefix="agent_clone_")

    try:
        repo_url = state["repo_url"]
        subprocess.run(
            ["git", "clone", repo_url, dest_dir],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,  # don't hang forever on a bad/huge repo
        )

        # Bug 6: generate a unique thread_id for Docker sandbox tracking
        thread_id = str(uuid.uuid4())

        # Bug 6: discover test files in the repo for the test node
        from pathlib import Path
        test_files = list(Path(dest_dir).rglob("test_*.py")) + list(Path(dest_dir).rglob("*_test.py"))
        file_path = str(test_files[0]) if test_files else ""

        return {
            'clone_result': CloneResult(success=True, repo_path=dest_dir),
            'repo_path': dest_dir,
            'thread_id': thread_id,
            'file_path': file_path,
        }

    except subprocess.CalledProcessError as e:
        return {'clone_result' :CloneResult(
            success=False,
            error_message=f"git clone failed (exit {e.returncode}):\n{e.stderr}",
        ),'repo_path':""}
    except subprocess.TimeoutExpired:
        return {'clone_result': CloneResult(success=False, error_message="git clone timed out after 120s"),'repo_path':""}
    except FileNotFoundError:
        return {'clone_result' : CloneResult(success=False, error_message="git is not installed or not in PATH"),'repo_path':""}
