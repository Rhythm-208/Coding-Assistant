from State import AgentState
from llm import propose_rewrite_agent as agent

SYSTEM_PROMPT = """You are a senior engineer writing a code fix.

You will be given a hypothesis about a bug. To read a file, you MUST use the native function calling feature to invoke the `read_file_exact` tool. Do NOT output raw JSON text to call the tool.

AFTER you have successfully read the file contents using the tool and figured out the fix, you must provide your proposed changes.
Your final response must be ONLY SEARCH/REPLACE blocks. Do NOT include any explanation or preamble.

Format for each file change:
--- filepath.py
<<<<
original code to replace exactly as it appears in the file
====
new replacement code
>>>>

Rules:
- The `original code` in the `<<<<` block MUST exactly match the file's current contents (including whitespace and indentation).
- The `filepath.py` must be the absolute path you read.
- You can include multiple SEARCH/REPLACE blocks for the same file or multiple files.
- Do not modify any file whose path contains "test".
- If prior attempts are shown and they failed, do not repeat the same change.
"""

def _content_to_text(content):
    """AIMessage.content can be a plain string OR a list of content blocks
    (e.g. [{'type': 'text', 'text': '...'}]) depending on the SDK version.
    Normalize to a plain string either way."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content) if content is not None else ""

def _get_final_ai_text(messages):
    """Walk backward to find the last AIMessage that is an actual final
    answer (not just a tool-call request), and return its text content."""
    for msg in reversed(messages):
        if getattr(msg, "type", None) != "ai":
            continue
        if getattr(msg, "tool_calls", None):
            # This AI turn was just invoking a tool, not the final diff.
            continue
        return _content_to_text(msg.content)
    return ""

def propose_patch(state: AgentState):
    changes = state.get("changes_to_make", [])
    current_change = changes[0] if changes else None

    if current_change:
        file_to_edit = current_change.get("file", "")
        instruction = current_change.get("instruction", "")
        
        user_prompt = f"""You are a senior software engineer.

MESSAGE: {state.get('message', state.get('prompt', ''))}
DIAGNOSIS: {state.get('Diagnose')}
REPO_PATH: {state.get('repo_path')}

CURRENT TASK: You need to modify the file: {file_to_edit}
INSTRUCTION: {instruction}

Use the native function calling feature to invoke the `read_file_exact` tool to inspect the exact contents of {file_to_edit}. Do NOT output JSON text directly. CRITICAL: You MUST use absolute paths when calling read_file_exact. AFTER you have read the file, propose your changes using ONLY the SEARCH/REPLACE block format — no explanation, preamble, or markdown code fences. Your entire final response must be parseable SEARCH/REPLACE blocks."""
        
        inputs = {
            "messages": [("system", SYSTEM_PROMPT),
                         ("user", user_prompt),
                         ]
        }
        response = agent.invoke(inputs)

        diff_text= _get_final_ai_text(response["messages"])

        return {
            "Propose_change": diff_text, 
            "current_change": current_change,
            "changes_to_make": changes[1:] # Pop the processed change
        }
    else:
        # Fallback for the old workflow
        user_prompt = f"""You are a senior software engineer.

MESSAGE: {state.get('message', state.get('prompt', ''))}
DIAGNOSIS: {state.get('Diagnose')}
REPO_PATH: {state.get('repo_path')}

Use the native function calling feature to invoke the `read_file_exact` tool to inspect the exact contents of the files mentioned in the diagnosis. Do NOT output JSON text directly. CRITICAL: You MUST use absolute paths (e.g., {state.get('repo_path')}/filename.py) when calling read_file_exact. AFTER you have read the files, propose your changes using ONLY the SEARCH/REPLACE block format — no explanation, preamble, or markdown code fences. Your entire final response must be parseable SEARCH/REPLACE blocks."""

        inputs = {
            "messages": [("system", SYSTEM_PROMPT),
                         ("user", user_prompt),
                         ]
        }
        response = agent.invoke(inputs)

        diff_text= _get_final_ai_text(response["messages"])

        return {"Propose_change": diff_text}
