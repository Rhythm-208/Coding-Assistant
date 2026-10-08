from State import AgentState, ApplyResult
from pathlib import Path

from nodes.Patch_matching import apply_match
from utils.file_persist import apply_changes
from langsmith import traceable


@traceable(name="apply_diff")
def apply_diff(state: AgentState, auto_apply: bool = False) -> dict:
    validation = state.get('validation_result')
    if not validation:
        return {'apply_diff': ApplyResult(success=False, error_message="No validation result found.")}

    if not validation.valid:
        return {'apply_diff': ApplyResult(
            success=False,
            error_message=f"Cannot apply - diff failed validation: {validation.reason}",
        )}

    # read the ACTUAL structured patch, not a stringified/parsed version of it -
    # validation_result only carries the verdict, Propose_change is the source of truth
    patch = state.get("Propose_change")
    if not patch or not patch.blocks:
        return {'apply_diff': ApplyResult(
            success=False,
            error_message="No proposed patch blocks found to apply.",
        )}

    current_change = state.get("current_change")
    target_file = current_change.get("file") if current_change else None

    try:
        vf = state.get("virtual_files")
        virtual_files = vf.copy() if vf else {}

        import os
        for block in patch.blocks:
            filepath = block.file_path

            if target_file:
                norm_filepath = os.path.normpath(filepath)
                norm_target = os.path.normpath(target_file)
                if norm_filepath != norm_target and not norm_target.endswith(os.sep + norm_filepath):
                    if Path(target_file).name == Path(filepath).name or not os.path.isabs(filepath):
                        filepath = target_file
                    else:
                        raise ValueError(f"Attempted to modify {filepath}, but current target is {target_file}")
                else:
                    filepath = target_file
                # new file creation - set entire content directly
                virtual_files[filepath] = block.replace
                continue

            content = virtual_files.get(filepath)
            if content is None:
                content = Path(filepath).read_text(encoding="utf-8", errors="ignore")

            # uses the SAME matcher validate_diff already confirmed would
            # succeed - this can only fail here if something changed the
            # file between validation and apply (e.g. a prior block in
            # this same patch already modified it), never due to the
            # validate/apply logic disagreeing with itself
            new_content = apply_match(block.search, block.replace, content)
            if new_content is None:
                raise ValueError(f"Search block for {filepath} no longer matches - file may have changed since validation.")

            virtual_files[filepath] = new_content

    except Exception as e:
        return {'apply_diff': ApplyResult(
            success=False,
            error_message=f"Failed to apply patch blocks: {str(e)}",
        )}

    if auto_apply:
        for filepath, new_content in virtual_files.items():
            apply_changes(filepath, new_content)

    return {
        'apply_diff': ApplyResult(success=True),
        'virtual_files': virtual_files,
        'changes_to_make': state.get("changes_to_make", [])[1:],
    }



