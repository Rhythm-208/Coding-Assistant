import subprocess
import tempfile
from dataclasses import dataclass
from ..State import AgentState,CloneResult

#Point to keep to check:
def route_after_clone(state: AgentState) -> str:
    if not state["clone_result"].success:
        return "escalate"       # or "failed", whatever you name your end/error node
    return "diagnose"

def clone_repo(state:AgentState):
    """
    Clones repo_url into a fresh temp directory. Never touches an
    existing folder - always creates its own, so there's no risk of
    cloning into something that already has unrelated files in it.
    """
    repo_url =state["repo_url"]
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
        return {'clone_result':CloneResult(success=True, repo_path=dest_dir),'repo_path':dest_dir}

    except subprocess.CalledProcessError as e:
        return {'clone_result' :CloneResult(
            success=False,
            error_message=f"git clone failed (exit {e.returncode}):\n{e.stderr}",
        ),'repo_path':""}
    except subprocess.TimeoutExpired:
        return {'clone_result': CloneResult(success=False, error_message="git clone timed out after 120s"),'repo_path':""}
    except FileNotFoundError:
        return {'clone_result' : CloneResult(success=False, error_message="git is not installed or not in PATH"),'repo_path':""}
