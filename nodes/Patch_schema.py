"""
Structured patch schema - replaces the hand-written <<<<>>>> text parser.

With this, the LLM API itself enforces the shape (every block really has
file_path/search/replace, nothing is ever silently missing a field, no
marker drift is even possible since there are no markers for the model
to get slightly wrong). This fully eliminates the entire category of
"the parser didn't recognize the format" failures.

It does NOT fix content-accuracy issues (search text not exactly
matching the file) - see validate_diff.py's fuzzy-match fallback for that.
"""

from pydantic import BaseModel, Field
from typing import List


class SearchReplaceBlock(BaseModel):
    file_path: str = Field(description="Path to the file, relative to the repo root")
    search: str = Field(
        description="The EXACT existing code to find and replace, copied verbatim "
                    "from the file content you were shown. Keep this as SHORT as "
                    "possible while still being unique in the file - a few lines, "
                    "not a whole function, unless the whole function is changing. "
                    "Leave empty only when creating a brand new file."
    )
    replace: str = Field(description="The new code that should replace the search block")


class ProposedPatch(BaseModel):
    blocks: List[SearchReplaceBlock] = Field(
        description="One or more search/replace edits, possibly across multiple files"
    )