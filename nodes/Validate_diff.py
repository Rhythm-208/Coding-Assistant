from State import AgentState, ValidationResult
from dataclasses import dataclass
from pathlib import Path

import re


def _is_test_file(file_path: str) -> bool:
    """Block any path that looks like a test file."""
    path_lower = file_path.lower()
    return (
            "test_" in path_lower
            or "_test.py" in path_lower
            or path_lower.startswith("tests/")
            or "/tests/" in path_lower
    )


def parse_search_replace_blocks(text: str):
    blocks = []
    lines = text.splitlines(keepends=True)
    current_file = None
    state = "looking_for_file"
    search_lines = []
    replace_lines = []

    for line in lines:
        if line.startswith("--- "):
            current_file = line[4:].strip()
            state = "looking_for_start"
        elif line.strip() == "<<<<":
            state = "in_search"
            search_lines = []
        elif line.strip() == "====" and state == "in_search":
            state = "in_replace"
            replace_lines = []
        elif line.strip() == ">>>>" and state == "in_replace":
            blocks.append({
                "file": current_file,
                "search": "".join(search_lines),
                "replace": "".join(replace_lines)
            })
            state = "looking_for_start"
        else:
            if state == "in_search":
                search_lines.append(line)
            elif state == "in_replace":
                replace_lines.append(line)
    return blocks


def _strip_markdown_fences(diff_text: str) -> str:
    """
    Models love wrapping diffs in ```diff ... ``` even when told not to.
    Strip that off if present. Extracts the code block robustly.
    """
    text = diff_text.strip()

    match = re.search(r'```(?:diff|patch)?\s*\n(.*?)\n```', text, re.DOTALL)
    if match:
        return match.group(1).strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # last-resort: strip stray fences glued to content with no newline
    text = re.sub(r'^```\w*\s*', '', text)
    text = re.sub(r'```\s*$', '', text)

    return text.strip()


def validate_diff(state: AgentState):
    diff_text = state.get("Propose_change")
    iteration = state.get("iteration", 0)

    if not diff_text:
        err = "Diff text is empty"
        return {'validation_result': ValidationResult(valid=False, reason=err),
                'iteration': iteration + 1,
                'Prev_Failed_Diagnose': [("assistant", f"Failed diff validation: {err}")]}

    cleaned = _strip_markdown_fences(diff_text)

    if not cleaned:
        err = "Diff text is empty after cleaning."
        return {'validation_result': ValidationResult(valid=False, reason=err),
                'iteration': iteration + 1,
                'Prev_Failed_Diagnose': [("assistant", f"Failed diff validation: {err}")]}

    blocks = parse_search_replace_blocks(cleaned)
    if not blocks:
        err = "No valid SEARCH/REPLACE blocks found in diff text."
        return {'validation_result': ValidationResult(valid=False, reason=err),
                'iteration': iteration + 1,
                'Prev_Failed_Diagnose': [("assistant", f"Failed diff validation: {err}\nDiff was:\n{cleaned}")]}

    touched_files = list(set([b["file"] for b in blocks if b["file"]]))

    blocked = [f for f in touched_files if _is_test_file(f)]
    if blocked:
        err = f"Diff modifies test file(s), which is not allowed: {blocked}"
        return {'validation_result': ValidationResult(valid=False,
            reason=err,
            touched_files=touched_files),
            'iteration': iteration + 1,
            'Prev_Failed_Diagnose': [("assistant", f"Failed diff validation: {err}")]}
            
    for b in blocks:
        filepath = b["file"]
        if not filepath:
            err = "A block is missing a filepath (missing --- filepath)."
            return {'validation_result': ValidationResult(valid=False, reason=err),
                    'iteration': iteration + 1,
                    'Prev_Failed_Diagnose': [("assistant", f"Failed diff validation: {err}")]}
        try:
            content = Path(filepath).read_text()
            if b["search"] not in content:
                err = f"SEARCH block exact match not found in {filepath}."
                return {'validation_result': ValidationResult(valid=False, reason=err),
                        'iteration': iteration + 1,
                        'Prev_Failed_Diagnose': [("assistant", f"Failed diff validation: {err}\nSearch block:\n{b['search']}")]}
        except Exception as e:
             err = f"Error reading {filepath} for validation: {str(e)}"
             return {'validation_result': ValidationResult(valid=False, reason=err),
                     'iteration': iteration + 1,
                     'Prev_Failed_Diagnose': [("assistant", f"Failed diff validation: {err}")]}

    return {'validation_result': ValidationResult(valid=True, cleaned_diff=cleaned, touched_files=touched_files)}


def route_after_validation(state: AgentState) -> str:
    """Guard rail: only proceed to apply_diff if the diff is valid."""
    vr = state.get("validation_result")
    if vr and vr.valid:
        return "apply_diff"

    if state.get("iteration", 0) >= state.get("max_iterations", 5):
        return "escalate"
    return "Diagnose"

