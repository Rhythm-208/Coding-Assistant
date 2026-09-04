from State import AgentState , ApplyResult
from pathlib import Path
from nodes.Validate_diff import parse_search_replace_blocks

# Import persistence helper
from utils.file_persist import apply_changes

# add guard rrail to check if the diff is validated

def apply_diff(state: AgentState, auto_apply: bool = False):
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
        virtual_files = state.get("virtual_files", {}).copy()
        
        for b in blocks:
            filepath = b["file"]
            if target_file and filepath != target_file:
                # Enforce that only the target file is modified
                raise ValueError(f"Attempted to modify {filepath}, but current target is {target_file}")
                
            # read from virtual_files if available, otherwise from disk
            content = virtual_files.get(filepath)
            if content is None:
                content = Path(filepath).read_text()
                
            if b["search"] not in content:
                raise ValueError(f"Search block not found in {filepath} during apply.")
            
            # replace only the first occurrence
            new_content = content.replace(b["search"], b["replace"], 1)
            virtual_files[filepath] = new_content
            
    except Exception as e:
         return {'apply_diff': ApplyResult(
            success=False,
            error_message=f"Failed to apply SEARCH/REPLACE blocks: {str(e)}",
        )}

    # Persist changes to real files if auto_apply is requested.
    # Loop over ALL modified files — fixes the previous single-file bug.
    if auto_apply:
        for filepath, new_content in virtual_files.items():
            apply_changes(filepath, new_content)

    return {'apply_diff': ApplyResult(success=True), 'virtual_files': virtual_files}




