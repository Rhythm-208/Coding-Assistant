# Coding-Assistant

An AI coding assistant built on [LangGraph](https://github.com/langchain-ai/langgraph) that diagnoses issues in a codebase, plans a set of file changes, writes patches, validates and tests them in an isolated Docker sandbox, and asks for human approval before anything is written back to disk. It's exposed over a FastAPI chat endpoint intended for an editor integration (e.g. a VS Code extension).

## How it works

There are two layers:

1. **Chat agent** (`Agent2.py`) — a conversational LangGraph agent (Gemini 2.5 Flash by default) that talks to the user, holds the conversation thread, and has a single tool, `run_assistant`, which delegates any actual code change to the workflow below.
2. **Assistant workflow** (`Assistant.py`) — a `StateGraph` that does the real work: diagnosing the problem, proposing a plan, generating diffs, validating and applying them, running the result in a sandboxed container, and pausing for human-in-the-loop (HITL) review at key checkpoints.

The chat agent and the workflow communicate through LangGraph's `interrupt()` / `Command(resume=...)` mechanism, so a long-running workflow can pause mid-graph, surface a question to the user in chat, and resume exactly where it left off once they reply.

### Workflow graph (`Assistant.py`)

```
initialize_workspace
        │
        ▼
     Diagnose ◄────────────────────────┐
        │                              │
        ▼                              │
  propose_changes                      │
        │                              │
        ▼                              │
   plan_review  (HITL: approve/reject/edit)
        │
        ▼
  propose_patch ◄───┐                  │
        │            │                 │
        ▼            │                 │
  validate_diff ──────┘ (invalid → Diagnose, or → escalate)
        │
        ▼
   apply_diff ──► (more files? → propose_patch)
        │
        ▼
   test_node  (runs in a Docker sandbox) ──(fail, retries left)──► Diagnose
        │
        ▼ (pass)
  human_approval  (HITL: commit y/n)
        │
        ▼
       END
```

- **`initialize_workspace`** — walks `repo_path`, builds a file listing, and creates a workflow thread id.
- **`Diagnose`** — a ReAct agent (reads files via `read_file_numbered` / `read_file_exact` / `list_folder_content`) that investigates the issue and produces a diagnosis.
- **`propose_changes`** — turns the diagnosis into a structured plan: a list of `{file, instruction}` changes plus an entry-point file to run for a sanity check.
- **`plan_review`** — **pauses the graph** (`interrupt`) and shows the plan to the user. They can approve, reject, or send free-text feedback that loops back into `propose_changes`.
- **`propose_patch`** — for each planned file, a dedicated LLM writes the fix as `SEARCH/REPLACE` diff blocks (never full-file rewrites), reading the exact current file contents first.
- **`validate_diff`** — parses the SEARCH/REPLACE blocks, checks they cleanly match the file content, and blocks any edits to test files.
- **`apply_diff`** — writes the validated change to disk (or virtual file store) and loops back to `propose_patch` until every planned file is done.
- **`test_node`** — copies the repo into a `python:3.11-slim` Docker container and runs the target file, capturing pass/fail/timeout.
- **`human_approval`** — **pauses the graph** again, shows the final diff (which already passed tests), and waits for the user to commit or discard it.
- **`escalate`** — reached after too many failed iterations (`max_iterations`); ends the run without applying anything.

### Chat layer (`Agent2.py`)

- Exposes `POST /sessions` with `{ message, thread_id, repo_path }`, returning `{ response }`.
- Maintains per-session state: a cached chat agent, the session's `repo_path`, and any pending workflow interrupt.
- `INTERRUPT_HANDLERS` maps each interrupt `type` (currently `plan_review`, `human_approval`, plus a generic fallback) to a pair of functions: one that turns the raw interrupt payload into a chat message, and one that turns the user's typed reply (`y`/`n`/free text) back into the structured payload the paused node expects.
- When a workflow is paused, the next chat message is routed straight to resuming it (`Command(resume=...)`) instead of going through the LLM again.

## Repo layout

| File | Purpose |
|---|---|
| `Agent2.py` | Current FastAPI chat server + HITL interrupt registry (main entry point). |
| `Assistant.py` | The compiled LangGraph workflow used by `Agent2.py`. |
| `State.py` | `AgentState` (TypedDict) and the `ValidationResult` / `TestResult` / `ApplyResult` dataclasses shared across nodes. |
| `llm.py` | Central LLM factory — rate-limited Gemini / OpenAI / local (Ollama-compatible) models, plus the pre-built ReAct agents used by each node. |
| `tools.py` | File and shell tools available to the LLM agents (`read_file_numbered`, `read_file_exact`, `list_folder_content`, `write_file`, `run_shell_command`). |
| `nodes/` | One module per graph node — `Initialize`, `Diagnose`, `Propose_changes`, `Plan_review`, `Propose_rewrite`, `Validate_diff`, `Apply_diff`, `test`, `HITL`, `Routing`, `Routing_changes`. |
| `Agent.py` | Earlier, simpler chat-agent prototype (single tool, no interrupt registry). Superseded by `Agent2.py`. |
| `Fixing_issue.py` | Earlier standalone version of the workflow graph (no plan review, references a `nodes.commit` module not present in this repo). Superseded by `Assistant.py`. |

## Requirements

No `requirements.txt` is currently checked in. Based on the imports used, you'll need:

```
fastapi
uvicorn
pydantic
python-dotenv
langchain
langchain-core
langgraph
langgraph-checkpoint
langsmith
docker              # Python Docker SDK — a running Docker daemon is required for test_node
langchain-google-genai   # if using Gemini models
langchain-openai         # if using OpenAI or an OpenAI-compatible local endpoint
```

You'll also need:
- **Docker** running locally, since `test_node` spins up a `python:3.11-slim` container to execute the target file.
- A `.env` file at the repository root with (at minimum):
  ```
  LANGSMITH_API_KEY=...       # required — llm.py raises if this is missing
  GOOGLE_API_KEY=...          # if using the default Gemini models
  # or
  LOCAL_LLM_ENDPOINT=http://localhost:11434/v1   # to use a local Ollama-compatible model instead
  ```

## Running it

```bash
pip install -r requirements.txt   # once one exists — see above for the inferred list
python Agent2.py                  # serves on http://0.0.0.0:8000
```

Then send chat turns to it:

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"message": "Fix the auth bypass bug", "thread_id": "demo", "repo_path": "/path/to/your/repo"}'
```

The response will either be a normal chat reply, or — once the workflow kicks in — a plan for you to approve/reject/edit, followed later by a diff to approve before anything is written to your repo.

## Notes

- Diffs are always generated as targeted `SEARCH/REPLACE` blocks rather than full-file rewrites, and files matching test-path patterns are never modified.
- Every workflow run gets its own `thread_id`, separate from the chat session's `thread_id`, so the underlying LangGraph checkpointer can track multiple in-flight workflows without cross-talk.
- `max_iterations` (default 4 in `Agent2.py`) bounds the Diagnose → patch → test retry loop before the run escalates instead of looping forever.

## Last Improvements

### 1. Yes / No Buttons for HITL Instead of Typing `y` / `n`

The current HITL checkpoints (`plan_review` and `human_approval`) require the user to type `y` or `n` in plain text. This is error-prone and feels raw. The improvement would replace free-text input with explicit **Yes** and **No** action buttons surfaced directly in the chat UI (or a dedicated review panel in the VS Code extension). The interrupt handler on the backend already receives a structured payload, so the front-end only needs to send the correct pre-formed string — no backend change is strictly required, but the `INTERRUPT_HANDLERS` in `Agent2.py` should be updated to accept a cleaner boolean/enum payload for robustness.

### 2. Show Diffs Inside the Actual File (Inline Diff View)

At the `human_approval` checkpoint the workflow currently prints the `SEARCH/REPLACE` diff blocks as raw text in the chat. The improvement would render the diff **inline inside the affected file** — i.e., open a diff editor tab (VS Code's built-in `vscode.diff` command) that shows the original file on the left and the proposed change on the right, with additions highlighted in green and deletions in red. This gives the reviewer full context (surrounding code, imports, indentation) instead of an isolated patch snippet. The `apply_diff` node already holds both the original content and the patched content in state, so exposing them through the interrupt payload is straightforward.

### 3. Overall Workflow Improvements

Several areas where the workflow can be made smarter and more reliable:

- **Parallel patch generation** — `propose_patch` currently processes planned files sequentially. Files that are independent of each other could be patched in parallel (e.g. via `asyncio.gather`) to cut wall-clock time on multi-file fixes.
- **Smarter retry routing** — when `validate_diff` fails, the graph currently routes back to `Diagnose`. A lighter alternative would be to route back only to `propose_patch` with the validation error injected into the prompt, avoiding a full re-diagnosis for what is often just a whitespace or context-mismatch issue.
- **Incremental test feedback** — `test_node` captures stdout/stderr from Docker but only surfaces a pass/fail signal to the retry loop. Passing the captured error output directly into the `Diagnose` prompt on the next retry would give the LLM much richer signal and reduce unnecessary iterations.
- **Persistent virtual file store** — `apply_diff` writes to disk immediately. Keeping changes in an in-memory virtual store until `human_approval` is granted would make the "discard" path a no-op (no rollback needed) and prevent partial writes from leaving the repo in a broken state if the session is interrupted.
- **Plan diffing on re-plan** — when the user rejects a plan and provides feedback, the new plan is shown in full. Highlighting what *changed* between the previous plan and the revised one (added/removed/modified steps) would help the user quickly verify their feedback was incorporated.
