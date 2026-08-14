from State import AgentState
from llm import llm
from pydantic import BaseModel, Field
from typing import List

class FileChange(BaseModel):
    file: str = Field(description="Absolute path to the file to change")
    instruction: str = Field(description="Specific instruction for what to change in the file")

class ChangesList(BaseModel):
    changes_to_make: List[FileChange]

SYSTEM_PROMPT = """You are a senior engineer planning a codebase fix.

You are given a DIAGNOSIS of an issue. Your task is to determine the list of files that need to be changed, and a specific instruction for what to change in each file.
"""

def propose_changes(state: AgentState):
    user_prompt = f"""
TITLE: {state.get('issue_title')}
DESCRIPTION: {state.get('issue_description')}
DIAGNOSE: {state.get('Diagnose')}
REPO_PATH: {state.get('repo_path')}

Determine the files to change and the instructions.
"""
    
    structured_llm = llm.with_structured_output(ChangesList)
    
    messages = [
        ("system", SYSTEM_PROMPT),
        ("user", user_prompt)
    ]
    
    response = structured_llm.invoke(messages)
    
    # Convert Pydantic objects to dicts for the state
    changes = [change.model_dump() for change in response.changes_to_make] if response else []
    
    return {"changes_to_make": changes}
