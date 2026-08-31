from typing import TypedDict, List, Annotated , Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from dataclasses import dataclass, field



@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""              # why it failed, if it did
    cleaned_diff: str = ""         # diff text with markdown fences stripped, ready to apply
    touched_files: list[str] = field(default_factory=list)

@dataclass
class TestResult:
    passed:bool
    outcome: str = "" # "passed" | "failed" | "timeout"
    failure_text: str = ""


@dataclass
class ApplyResult:
    success: bool
    error_message: str = ""

class AgentState(TypedDict):
    # --- Shared fields (both workflows) ---
    repo_path: str

    messages: Annotated[List[BaseMessage],add_messages]

    Propose_change: Optional[str]

    validation_result: Optional[ValidationResult]

    apply_diff : Optional[ApplyResult]

    thread_id: Optional[str]
    file_path: Optional[str] # The script to run in the sandbox for testing
    repo_files: Optional[List[str]]
    test_result: Optional[TestResult]
    virtual_files: Optional[dict] # tracks modified file content without writing to disk

    plan_approval_status: Optional[str] # "approved", "rejected", "edit"
    plan_feedback: Optional[str]
    plan_review_skipped: Optional[bool]

    approved: Optional[bool]

    status: Optional[str]  # "done" | "rejected" | "escalated" | "failed"

    iteration: int
    max_iterations: int

    Prev_Failed_Diagnose : Annotated[List[BaseMessage],add_messages]

    # --- Fixing_issue workflow fields ---
    message: Optional[str]
    Diagnose: Optional[str]

    # --- Changes workflow fields ---
    prompt: Optional[str]           # user's natural-language change request
    Analysis: Optional[str]         # analyze node's understanding of what to change

    # --- Assistant Workflow specific tracking fields ---
    changes_to_make: list[dict]
    current_change: Optional[dict]
