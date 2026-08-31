from State import AgentState
from llm import llm
from pydantic import BaseModel, Field
from typing import List

class FileChange(BaseModel):
    file: str = Field(description="Absolute path to the file to change")
    instruction: str = Field(description="Specific instruction for what to change in the file")

class ChangesList(BaseModel):
    changes_to_make: List[FileChange]
    file_path: str = Field(description="The absolute path of a single file in the repository that should be executed to verify the code runs without errors.")

SYSTEM_PROMPT = """You are a senior engineer planning a codebase fix.

You are given a DIAGNOSIS of an issue. Your task is to determine:
1. The list of files that need to be changed, and a specific instruction for what to change in each file.
2. The absolute path of a single file in the repository that can be run (e.g., the main entrypoint or a relevant script) to check if the changes successfully run without errors.
"""

def propose_changes(state: AgentState):
    plan_feedback = state.get('plan_feedback')
    feedback_section = f"\nPREVIOUS PLAN FEEDBACK:\nThe user reviewed your previous plan and provided the following feedback/edit request: {plan_feedback}\nPlease incorporate this feedback into your new plan.\n" if plan_feedback else ""

    user_prompt = f"""
MESSAGE: {state.get('message', state.get('prompt', ''))}
DIAGNOSE: {state.get('Diagnose')}
REPO_PATH: {state.get('repo_path')}
{feedback_section}
Determine the files to change and the instructions.
"""
    
    structured_llm = llm.with_structured_output(ChangesList)
    
    messages = [
        ("system", SYSTEM_PROMPT),
        ("user", user_prompt)
    ]
    
    response = structured_llm.invoke(messages)
    
    # Convert Pydantic objects to dicts for the state
    if response:
        changes = [change.model_dump() for change in response.changes_to_make]
        file_path = response.file_path
    else:
        changes = []
        file_path = ""
    
    return {"changes_to_make": changes, "file_path": file_path}
