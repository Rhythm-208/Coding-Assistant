/**
 * Thin HTTP client for the Agent2.py FastAPI server.
 *
 * The server exposes a single endpoint:
 *   POST /sessions
 *   body: { message: string, thread_id: string, repo_path: string }
 *   returns: { response: string }
 *
 * It handles both a normal chat turn AND resuming a paused workflow
 * (plan review / human approval) transparently — from the extension's
 * point of view it's always "send a message, get an AI message back".
 */

export interface AgentChatRequest {
  message: string;
  thread_id: string;
  repo_path: string;
}

export interface AgentChatResponse {
  response: string;
}

const DEFAULT_BASE_URL = 'http://localhost:8000';

export class AgentApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = 'AgentApiError';
  }
}

/**
 * Sends one chat turn to the agent and returns its reply text.
 *
 * @param message   The user's message (a question, instruction, or a
 *                  plain 'y'/'n'/feedback reply to a pending plan/diff).
 * @param threadId  Stable id for this chat session (used as LangGraph
 *                  checkpoint thread_id on the server).
 * @param repoPath  Absolute path to the repo the agent should operate on.
 * @param baseUrl   Override for the Agent2.py server base URL.
 */
export async function sendMessageToAgent(
  message: string,
  threadId: string,
  repoPath: string,
  baseUrl: string = DEFAULT_BASE_URL
): Promise<string> {
  let res: Response;

  try {
    res = await fetch(`${baseUrl}/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        thread_id: threadId,
        repo_path: repoPath,
      } satisfies AgentChatRequest),
    });
  } catch (err) {
    throw new AgentApiError(
      `Could not reach agent server at ${baseUrl}. Is Agent2.py running? (${(err as Error).message})`
    );
  }

  if (!res.ok) {
    let detail = '';
    try {
      const body = (await res.json()) as { detail?: string };
      detail = body?.detail ?? JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => '');
    }
    throw new AgentApiError(`Agent request failed (${res.status}): ${detail}`, res.status);
  }

  const data = (await res.json()) as AgentChatResponse;
  return data.response;
}