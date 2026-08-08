from typing import TypedDict, List, Annotated , Optional
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from dataclasses import dataclass, field



@dataclass
class CloneResult:
    success: bool
    repo_path: str = ""
    error_message: str = ""

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
    issue_title: str
    issue_description: str
    repo_url: str
    repo_path: str




    messages: Annotated[List[BaseMessage],add_messages]

    clone_result: CloneResult

    Diagnose: Optional[str]
    Propose_change: Optional[str]

    validation_result: Optional[ValidationResult]

    apply_diff : Optional[ApplyResult]

    thread_id: Optional[str]
    file_path: Optional[str]
    test_result: Optional[TestResult]

    status: Optional[str]  # "done" | "rejected" | "escalated" | "failed"

    iteration: int
    max_iterations: int


    Prev_Failed_Diagnose : Annotated[List[BaseMessage],add_messages]


