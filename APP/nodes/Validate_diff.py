"""
validate_diff.py - works off the structured ProposedPatch object, and
uses the SAME matching function apply_diff uses (see patch_matching.py)
so a block that validates is GUARANTEED to be appliable.
"""
 
from State import AgentState, ValidationResult
from pathlib import Path
from nodes.Patch_matching import find_match_range, apply_match
from langsmith import traceable
 
 
@traceable(name="validate_diff")
def validate_diff(state: AgentState) -> dict:
    patch = state.get("Propose_change")
    iteration = state.get("iteration", 0)
    virtual_files = state.get("virtual_files", {}).copy()
 
    if not patch or not patch.blocks:
        err = "No edit blocks were proposed."
        return {
            "validation_result": ValidationResult(valid=False, reason=err),
            "iteration": iteration + 1,
            "Prev_Failed_Diagnose": [("assistant", f"Failed diff validation: {err}")],
        }
 
    touched_files = list({b.file_path for b in patch.blocks if b.file_path})
 
    for block in patch.blocks:
        if not block.file_path:
            err = "A block is missing a file_path."
            return {
                "validation_result": ValidationResult(valid=False, reason=err),
                "iteration": iteration + 1,
                "Prev_Failed_Diagnose": [("assistant", f"Failed diff validation: {err}")],
            }
 
        if block.search == "":
            if block.file_path in virtual_files or Path(block.file_path).exists():
                err = f"{block.file_path} was treated as a new file but already exists - use a search/replace edit instead."
                return {
                    "validation_result": ValidationResult(valid=False, reason=err),
                    "iteration": iteration + 1,
                    "Prev_Failed_Diagnose": [("assistant", f"Failed diff validation: {err}")],
                }
            virtual_files[block.file_path] = block.replace
            continue
 
        try:
            content = virtual_files.get(block.file_path)
            if content is None:
                content = Path(block.file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            err = f"Error reading {block.file_path}: {e}"
            return {
                "validation_result": ValidationResult(valid=False, reason=err),
                "iteration": iteration + 1,
                "Prev_Failed_Diagnose": [("assistant", f"Failed diff validation: {err}")],
            }
 
        if find_match_range(block.search, content) is None:
            err = f"SEARCH block for {block.file_path} doesn't match the file's current content."
            return {
                "validation_result": ValidationResult(valid=False, reason=err),
                "iteration": iteration + 1,
                "Prev_Failed_Diagnose": [(
                    "assistant",
                    f"Failed diff validation for {block.file_path}: your SEARCH block was not "
                    f"found. Re-read the file's current content and copy the search text "
                    f"verbatim, keeping it short and unique.\n\nYour SEARCH block was:\n{block.search}"
                )],
            }
            
        new_content = apply_match(block.search, block.replace, content)
        if new_content is not None:
            virtual_files[block.file_path] = new_content
 
    return {
        "validation_result": ValidationResult(valid=True, cleaned_diff="", touched_files=touched_files)
    }
 
 
def route_after_validation(state: AgentState) -> str:
    vr = state.get("validation_result")
    if vr and vr.valid:
        return "apply_diff"
    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "escalate"
    return "propose_patch"
 