from pathlib import Path
from State import AgentState
from llm import llm
from langsmith import traceable

@traceable(name="analyze_repo")
def analyze_repo(state: AgentState) -> dict:
    repo_path = state.get("repo_path", "")
    issue_message = state.get("message", state.get("prompt", ""))
    
    skip_dirs = {".git", ".venv", "__pycache__", "node_modules", ".idea", ".vs"}
    root = Path(repo_path)
    
    file_summaries = state.get("file_summaries", {})
    
    if not file_summaries and root.exists():
        for file in sorted(root.rglob("*")):
            if any(part in skip_dirs for part in file.parts):
                continue
            if not file.is_file():
                continue
            if file.stat().st_size > 50_000:
                continue
            
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            
            rel = str(file.relative_to(root))
            
            # Just store the raw text instead of asking the LLM to summarize every single file
            file_summaries[rel] = text

    files_text = "\n\n".join(f"File: {path}\nContent:\n{content}" for path, content in file_summaries.items())
    
    project_prompt = f"""You are a senior software architect. 
Here is the source code of all files in the repository:

{files_text}

The user has reported the following issue/task:
{issue_message}

Please provide an overall architectural analysis of the project. Make sure to clearly explain:
1. The project structure and how the files relate to each other.
2. Which specific files are likely involved in the issue and why.
3. Any important considerations for implementing the task requested by the user.
"""
    project_res = llm.invoke(project_prompt)
    project_analysis = project_res.content if hasattr(project_res, 'content') else str(project_res)
    
    return {
        "file_summaries": file_summaries,
        "project_analysis": project_analysis,
        "Analysis": project_analysis
    }
