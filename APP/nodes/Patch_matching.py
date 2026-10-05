"""
Shared matching logic for validate_diff and apply_diff.

Previously these two files used DIFFERENT matching rules (validate used
a SequenceMatcher ratio-based fuzzy check; apply used a strict exact
substring check) - meaning a block could pass validation and then still
fail to apply. This module is the single source of truth both files
import, so that can no longer happen: if find_match_range() finds a
match, apply_match() is guaranteed to be able to use that exact same
match to perform the edit.

Matching is tolerant of trailing-whitespace/indentation differences per
line (the realistic source of LLM search-block flakiness), but requires
every line's CONTENT to match exactly otherwise - this is deliberately
stricter than a similarity-ratio approach, so it never "matches" the
wrong block just because it looks similar.
"""

from typing import Optional


def normalize_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]


def find_match_range(search_text: str, content_text: str) -> Optional[tuple[int, int]]:
    """
    Returns the (start, end) line-index range in content_text where
    search_text matches, or None if no match exists anywhere.
    """
    search_lines = normalize_lines(search_text)
    content_lines = normalize_lines(content_text)
    n = len(search_lines)

    if n == 0 or len(content_lines) < n:
        return None

    for i in range(len(content_lines) - n + 1):
        if content_lines[i:i + n] == search_lines:
            return i, i + n
    return None


def apply_match(search_text: str, replace_text: str, content_text: str) -> Optional[str]:
    """
    Finds the match and splices replace_text in. Everything OUTSIDE the
    matched region is preserved exactly as it was in the original content -
    only the matched lines themselves change, so this never silently
    reformats unrelated parts of the file even though matching itself is
    whitespace-tolerant.
    """
    match = find_match_range(search_text, content_text)
    if match is None:
        return None

    start, end = match
    original_lines = content_text.replace("\r\n", "\n").split("\n")
    replace_lines = replace_text.replace("\r\n", "\n").split("\n")
    new_lines = original_lines[:start] + replace_lines + original_lines[end:]
    return "\n".join(new_lines)