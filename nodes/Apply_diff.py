from State import AgentState , ApplyResult
from pathlib import Path
from nodes.Validate_diff import parse_search_replace_blocks

# add guard rrail to check if the diff is validated

def apply_diff(state: AgentState):
    validation = state['validation_result']

    if not validation.valid:
        return {'apply_diff': ApplyResult(
            success=False,
            error_message=f"Cannot apply - diff failed validation: {validation.reason}",
        )}

    diff_text = validation.cleaned_diff
    blocks = parse_search_replace_blocks(diff_text)
    
    if not blocks:
         return {'apply_diff': ApplyResult(
            success=False,
            error_message="No valid SEARCH/REPLACE blocks found to apply.",
        )}
        
    try:
        for b in blocks:
            filepath = b["file"]
            content = Path(filepath).read_text()
            if b["search"] not in content:
                raise ValueError(f"Search block not found in {filepath} during apply.")
            
            # replace only the first occurrence
            new_content = content.replace(b["search"], b["replace"], 1)
            Path(filepath).write_text(new_content)
    except Exception as e:
         return {'apply_diff': ApplyResult(
            success=False,
            error_message=f"Failed to apply SEARCH/REPLACE blocks: {str(e)}",
        )}

    return {'apply_diff': ApplyResult(success=True)}




