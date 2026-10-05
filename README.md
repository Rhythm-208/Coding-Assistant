# Coding-Assistant

An AI coding assistant built on [LangGraph](https://github.com/langchain-ai/langgraph) that diagnoses issues in a codebase, plans a set of file changes, writes patches, validates and tests them in an isolated Docker sandbox, and asks for human approval before anything is written back to disk. It's exposed over a FastAPI chat endpoint intended for an editor integration (e.g. a VS Code extension).

## Repository Structure

- `APP/`: The core Python backend. Contains the FastAPI server, the conversational agent (`APP/Agent2.py`), the LangGraph state machines (`APP/Assistant.py` and `APP/nodes/`), and the sandbox environment handlers.
- `FrontEnd/`: The VS Code extension (TypeScript/Node.js). Provides a graphical chat UI integrated right into the editor to communicate with the `APP/` backend, display proposed plans, show inline diffs, and handle human-in-the-loop (HITL) approvals seamlessly.

## How it works (Backend)

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
   plan_review  (HITL: approve/reject/edit)
        │
        ▼
  propose_patch ◄───┐
        │           │
        ▼           │
  validate_diff ────┘ (invalid → propose_patch, or → escalate)
        │
        ▼
   apply_diff ──► (more files? → propose_patch)
        │ (no more files)
        ▼
   test_node  (runs in a Docker sandbox) ──(fail, retries left)──► Diagnose
        │
        ▼ (pass)
 diff_review_hitl (HITL: per-file accept/decline)
        │
        ▼
 persist_approved (writes changes to disk)
        │
        ▼
       END
```

- **`initialize_workspace`** — walks `repo_path`, builds a file listing, and creates a workflow thread id.
- **`Diagnose`** — a ReAct agent (reads files via `read_file_numbered` / `read_file_exact` / `list_folder_content`) that investigates the issue, produces a diagnosis, and outputs a structured plan: a list of `{file, instruction}` changes plus an entry-point file to run for a sanity check.
- **`plan_review`** — **pauses the graph** (`interrupt`) and shows the plan to the user. They can approve, reject, or send free-text feedback that loops back into `Diagnose`.
- **`propose_patch`** — pops one planned file at a time. It uses a dedicated LLM to write the fix. For file creations, it outputs the full file content. For edits, it uses `SEARCH/REPLACE` diff blocks.
- **`validate_diff`** — parses the diff blocks, checks they cleanly match the current file content, and blocks edits to test files. Invalid diffs route back to `propose_patch`.
- **`apply_diff`** — applies the validated change to a memory `virtual_files` dictionary. If there are more files in the plan, it routes back to `propose_patch` to process the next one.
- **`test_node`** — copies the repo and the `virtual_files` into a `python:3.11-slim` Docker container and runs the target file, capturing pass/fail/timeout.
- **`diff_review_hitl`** — **pauses the graph** to present a rich, per-file diff review. The user can accept or decline changes on a per-file basis.
- **`persist_approved`** — takes the accepted files from `diff_review_hitl` and finally writes them to the actual disk.
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
| `nodes/` | One module per graph node — `Initialize`, `Diagnose`, `Plan_review`, `Propose_rewrite`, `Validate_diff`, `Apply_diff`, `test`, `HITL`, `Routing`, `Routing_changes`. |
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

## Running the Backend (APP)

```bash
pip install -r requirements.txt
python APP/Agent2.py              # serves on http://0.0.0.0:8000
```

Then send chat turns to it:

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"message": "Fix the auth bypass bug", "thread_id": "demo", "repo_path": "/path/to/your/repo"}'
```

The response will either be a normal chat reply, or — once the workflow kicks in — a plan for you to approve/reject/edit, followed later by a diff to approve before anything is written to your repo.

## Running the Frontend (VS Code Extension)

1. Open the `FrontEnd/Assistant2/vscode-agent-chat/` folder in VS Code.
2. Run `npm install` to install extension dependencies.
3. Press `F5` to open a new Extension Development Host window.
4. Open the Coding Assistant panel to interact directly with the backend running on port `8000`.

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

## Multi-File Edits & File Creation (Updated Quality)

The workflow has been fundamentally upgraded to robustly support multi-file edits and creating new files from scratch:

- **Iterative Patching:** The agent now processes each file sequentially via `propose_patch`. This isolates the LLM's context per file, significantly reducing hallucinations and syntax errors compared to generating a massive multi-file diff in a single prompt.
- **File Creation capability:** If a task requires a new file, the planner sets `action: "create"`. The patcher then bypasses `SEARCH/REPLACE` logic and directly outputs the complete content of the new file.
- **In-Memory Virtual Store:** File modifications are now strictly held in `virtual_files` (memory) and are passed along the graph state. The actual files on disk are completely untouched until the final `persist_approved` node, meaning discarded fixes leave zero mess on disk and no `git checkout` is required.
- **Smarter Retry Routing:** When `validate_diff` fails, the graph routes back to `propose_patch` rather than `Diagnose`. This saves an expensive LLM reasoning step, as the diagnosis remains valid and only the patch formatting or application failed.
- **Per-file HITL Review:** `human_approval` has been replaced with `diff_review_hitl`, which supports rejecting specific files from the patch while approving others, all seamlessly synced back to disk via `persist_approved`.

## Future Improvements

- **Parallel patch generation** — `propose_patch` currently processes planned files sequentially. Files that are independent of each other could be patched in parallel (e.g. via `asyncio.gather`) to cut wall-clock time on multi-file fixes.
- **Incremental test feedback** — `test_node` captures stdout/stderr from Docker but only surfaces a pass/fail signal to the retry loop. Passing the captured error output directly into the `Diagnose` prompt on the next retry would give the LLM much richer signal and reduce unnecessary iterations.
- **Plan diffing on re-plan** — when the user rejects a plan and provides feedback, the new plan is shown in full. Highlighting what *changed* between the previous plan and the revised one (added/removed/modified steps) would help the user quickly verify their feedback was incorporated.
