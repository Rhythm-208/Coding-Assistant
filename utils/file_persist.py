"""
Utility module for persisting edited node files to disk.

Provides:

    apply_changes(file_path, new_content)
        Write new_content to file_path directly on disk.

    build_diff_payload(virtual_files)
        Compute a structured per-file diff (hunks with line numbers) from the
        current virtual_files dict vs. what is currently on disk.
        Used to feed the frontend diff viewer before asking the user to accept.
"""

import difflib
from pathlib import Path
from typing import Optional


def apply_changes(file_path: str, new_content: str) -> None:
    """Persist ``new_content`` to ``file_path``.

    Parameters
    ----------
    file_path : str
        Absolute path to the target file.
    new_content : str
        Full file content to write (overwrites existing content).

    Raises
    ------
    OSError
        If the file cannot be written (e.g. permission denied).
    """
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_content, encoding="utf-8")


def _parse_hunks(diff_lines: list[str]) -> list[dict]:
    """
    Convert unified diff lines into a list of hunk dicts.

    Each hunk:
      {
        "old_start": int, "old_count": int,
        "new_start": int, "new_count": int,
        "lines": [{"type": "context"|"add"|"remove", "content": str}, ...]
      }
    """
    hunks: list[dict] = []
    current: Optional[dict] = None

    for raw in diff_lines:
        # Skip file header lines (--- / +++)
        if raw.startswith("--- ") or raw.startswith("+++ "):
            continue

        if raw.startswith("@@"):
            # e.g.  @@ -12,4 +12,5 @@
            import re
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", raw)
            if m:
                if current is not None:
                    hunks.append(current)
                current = {
                    "old_start": int(m.group(1)),
                    "old_count": int(m.group(2) or 1),
                    "new_start": int(m.group(3)),
                    "new_count": int(m.group(4) or 1),
                    "lines": [],
                }
        elif current is not None:
            if raw.startswith("+"):
                current["lines"].append({"type": "add", "content": raw[1:]})
            elif raw.startswith("-"):
                current["lines"].append({"type": "remove", "content": raw[1:]})
            else:
                current["lines"].append({"type": "context", "content": raw[1:] if raw.startswith(" ") else raw})

    if current is not None:
        hunks.append(current)

    return hunks


def build_diff_payload(virtual_files: dict) -> list[dict]:
    """
    Compute a structured per-file diff for all files in ``virtual_files``.

    For each file, reads the current on-disk version (or treats it as empty
    if the file doesn't exist yet), then computes a unified diff against the
    virtual (proposed) content and parses it into hunks with line numbers.

    Returns
    -------
    list[dict]
        One entry per modified file:
        {
          "file": str,
          "hunks": [
            {
              "old_start": int, "old_count": int,
              "new_start": int, "new_count": int,
              "lines": [{"type": "context"|"add"|"remove", "content": str}]
            },
            ...
          ]
        }

        Files with no diff (content identical to disk) are omitted.
    """
    result = []

    for filepath, new_content in virtual_files.items():
        # Read existing on-disk content (empty string if file doesn't exist yet)
        try:
            old_content = Path(filepath).read_text(encoding="utf-8")
        except FileNotFoundError:
            old_content = ""

        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=filepath,
            tofile=filepath,
            lineterm="",
        ))

        if not diff:
            continue  # file unchanged — skip

        hunks = _parse_hunks(diff)
        result.append({"file": filepath, "hunks": hunks})

    return result


