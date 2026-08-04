from json import tool
from pathlib import Path
from langchain.tools import tool

@tool
def read_file_numbered(file_path: str) -> str:
    """Read a file and return its content with line numbers prefixed.
        This is what we'll show the model so it can generate an accurate diff."""
    content = Path(file_path).read_text()
    lines = content.splitlines()
    numbered = [f"{i + 1}: {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered)

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








