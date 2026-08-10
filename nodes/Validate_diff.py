from State import AgentState , ValidationResult
from dataclasses import dataclass
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError



def _strip_markdown_fences(diff_text: str) -> str:
    """
        Models love wrapping diffs in ```diff ... ``` even when told not to.
        Strip that off if present. This is intentionally simple - if the
        model does something weirder than this, we WANT validation to fail
        loudly rather than silently guess.
     """

    text =  diff_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines)

    return text.strip()


def _is_test_file(file_path: str) -> bool:
    """Block any path that looks like a test file."""
    path_lower = file_path.lower()
    return (
            "test_" in path_lower
            or "_test.py" in path_lower
            or path_lower.startswith("tests/")
            or "/tests/" in path_lower
    )


def validate_diff(state: AgentState):
    diff_text = state["Propose_change"]
    if diff_text is None:
        return {'validation_result': ValidationResult(valid=False,reason="Diff text is empty")}


    cleaned = _strip_markdown_fences(diff_text)

    if not cleaned:
        return {'validation_result': ValidationResult(valid=False,reason="Diff text is empty after cleaning.")}

    try:
        patch_set = PatchSet(cleaned)

    except UnidiffParseError as e:
        return {'validation_result':ValidationResult(valid=False, reason=f"Diff did not parse: {e}")}

    touched_files = [pf.path for pf in patch_set]

    blocked = [f for f in touched_files if _is_test_file(f)]
    if blocked:
        return {'validation_result': ValidationResult(valid=False,
            reason=f"Diff modifies test file(s), which is not allowed: {blocked}",
            touched_files=touched_files)}

    return {'validation_result': ValidationResult(valid=True, cleaned_diff=cleaned, touched_files=touched_files)}


def route_after_validation(state: AgentState) -> str:
    """Guard rail: only proceed to apply_diff if the diff is valid."""
    vr = state.get("validation_result")
    if vr and vr.valid:
        return "apply_diff"

    # Invalid diff — retry or escalate
    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "escalate"
    return "Diagnose"


