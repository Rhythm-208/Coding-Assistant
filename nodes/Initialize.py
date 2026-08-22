import uuid
import os
from pathlib import Path
from State import AgentState

def initialize_workspace(state: AgentState):
    """
    Initializes workspace variables for the local directory.
    Generates a thread_id for docker isolation.
    """
    repo_path = state.get("repo_path", "")
    thread_id = str(uuid.uuid4())
    
    repo_files = []
    if repo_path and os.path.exists(repo_path):
        for root, dirs, files in os.walk(repo_path):
            # Exclude some noisy directories
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules', '.venv', 'venv', '.env')]
            
            # Get the relative path for the current folder
            rel_root = os.path.relpath(root, repo_path)
            if rel_root != ".":
                repo_files.append(rel_root)
            
            # Get relative paths for all files in the current folder
            for file in files:
                if rel_root == ".":
                    repo_files.append(file)
                else:
                    repo_files.append(os.path.join(rel_root, file))

    return {
        "thread_id": thread_id,
        "repo_files": repo_files,
    }
