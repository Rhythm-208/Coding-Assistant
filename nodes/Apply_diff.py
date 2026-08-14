from State import AgentState , ApplyResult
from pathlib import Path
from nodes.Validate_diff import parse_search_replace_blocks

# add guard rrail to check if the diff is validated

def apply_diff(state: AgentState):
    validation = state.get('validation_result')
    if not validation:
        return {'apply_diff': ApplyResult(success=False, error_message="No validation result found.")}

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
        
    current_change = state.get("current_change")
    target_file = current_change.get("file") if current_change else None
        
    try:
        for b in blocks:
            filepath = b["file"]
            if target_file and filepath != target_file:
                # Enforce that only the target file is modified
                raise ValueError(f"Attempted to modify {filepath}, but current target is {target_file}")
                
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




