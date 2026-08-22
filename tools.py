from json import tool
from pathlib import Path
from langchain.tools import tool
import subprocess
@tool
def read_file_numbered(file_path: str) -> str:
    """Read a file and return its content with line numbers prefixed.
        This is what we'll show the model so it can generate an accurate diff."""
    try:
        content = Path(file_path).read_text()
        lines = content.splitlines()
        numbered = [f"{i + 1}: {line}" for i, line in enumerate(lines)]
        return "\n".join(numbered)
    except FileNotFoundError:
        return f"Error: File not found at {file_path}. Please make sure to use the absolute path starting with REPO_PATH."
    except Exception as e:
        return f"Error reading file {file_path}: {str(e)}"

@tool
def read_file_exact(file_path: str) -> str:
    """Read a file and return its exact content.
        This is what we'll show the model so it can generate an exact SEARCH block."""
    try:
        content = Path(file_path).read_text()
        return content
    except FileNotFoundError:
        return f"Error: File not found at {file_path}. Please make sure to use the absolute path starting with REPO_PATH."
    except Exception as e:
        return f"Error reading file {file_path}: {str(e)}"

@tool
def list_folder_content(folder_path):
    """List all files and directories in a folder."""

    path = Path(folder_path)

    if not path.exists():
        return "Error: The path does not exist."
    if not path.is_dir():
        return "Error: The path is not a folder."

    folders = [item.name for item in path.iterdir() if item.is_dir()]
    files = [item.name for item in path.iterdir() if item.is_file()]

    return {
        "folders": folders,
        "files": files
    }

@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Overwrites the file if it exists."""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing to file {file_path}: {str(e)}"

@tool
def run_shell_command(command: str) -> str:
    """Run a shell command and return its output. This tool requires human approval before executing."""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        output = result.stdout
        if result.stderr:
            output += "\nSTDERR:\n" + result.stderr
        return output or "Command executed successfully with no output."
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:
        return f"Error executing command: {str(e)}"
