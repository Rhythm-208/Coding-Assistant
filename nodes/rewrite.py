from langchain_core.tools import tool
from pydantic import BaseModel,Field
from ..State import AgentState
from langgraph.prebuilt import InjectedState

from ..tools import read_file_numbered,list_folder_content
from typing import List , Annotated
import os
from langchain_deepseek import ChatDeepSeek
from langchain.agents import create_agent

from dotenv import load_dotenv
load_dotenv()

llm =  ChatDeepSeek(model="deepseek-chat")


class LineReplacement(BaseModel):
    line_number: int = Field(description="The 1-based index of the line to replace.")
    new_text : str = Field(description="The new text to replace at the specified line number.")


class ModifyFileInput(BaseModel):
    file_path:str
    replacements: List[LineReplacement] = Field(
        description="A list of line replacements to apply to the file."
    )

@tool("modify_file_lines", args_schema=ModifyFileInput)
def edit(file_path: str, replacements: List[LineReplacement] , state: Annotated[dict, InjectedState]) -> str:
    """
        Opens a specific file and replaces the provided line numbers with new text.
        Use this tool when you need to edit an existing file.
    """
    repo_path = state.get("repo_path",".")
    full_path = os.path.join(repo_path, file_path)

    if not os.path.exists(full_path):
        return f"Error: The file '{full_path}' does not exist."

    try:
        with open(full_path, "r",encoding="utf-8") as f:
            lines = f.readlines()
        total_lines = len(lines)

        for rep in replacements:
            idx = rep.line_number - 1  # Convert 1-based to 0-based index

            if 0 <= idx < total_lines:
                new_line = rep.new_text
                #  Preserve newline consistency
                if not new_line.endswith('\n'):
                    new_line += '\n'
                lines[idx] = new_line
            else:
                return (f"Error: Line number {rep.line_number} is out of bounds. "
                    f"The file only has {total_lines} lines.")

        with open(full_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return f"Success: Modified {len(replacements)} lines in '{full_path}'."

    except Exception as e:
        return f"An error occurred while modifying the file: {str(e)}"

agent  = create_agent(llm,tools = [edit,read_file_numbered,list_folder_content])


def rewrite(state: AgentState):
    prompt =  f"""You are a senior software engineer. Rewrite the code to solve this issue:
    TITLE: {state.get('issue_title')}
    DESCRIPTION: {state.get('issue_description')}
    DIAGNOSIS: {state.get('Diagnose')}
    
    Use your tools to explore the repo and edit the code to fix the issue.
    """

    inputs = {
        "messages": [
            ("user", prompt)
        ]
    }

    # FIX 2: Invoke the agent with the state dictionary
    respone = agent.invoke(inputs)
    return {'message': [respone]}


