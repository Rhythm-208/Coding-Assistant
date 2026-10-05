import * as vscode from 'vscode';
import { randomUUID } from 'crypto';
import { sendMessageToAgent, AgentApiError } from './agentClient';

/**
 * Webview sidebar that lets the user chat with the Agent2.py backend.
 * Every user message is sent with the current thread_id and the
 * workspace's repo_path; the AI reply is streamed back into the panel.
 */
export class ChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'aiCodingAssistant.chatView';

  private _view?: vscode.WebviewView;
  private _threadId: string = randomUUID();

  constructor(private readonly _extensionUri: vscode.Uri) {}

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this._extensionUri, 'media')],
    };

    webviewView.webview.html = this._getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (msg: { type: string; value?: string }) => {
      switch (msg.type) {
        case 'userMessage':
          await this._handleUserMessage(msg.value ?? '');
          break;
        case 'newSession':
          this._threadId = randomUUID();
          this._post('sessionReset', this._threadId);
          break;
      }
    });
  }

  /** Called from a command palette entry / button to start a fresh thread. */
  public startNewSession(): void {
    this._threadId = randomUUID();
    this._post('sessionReset', this._threadId);
  }

  private async _handleUserMessage(message: string): Promise<void> {
    const trimmed = message.trim();
    if (!trimmed) {
      return;
    }

    const repoPath = this._getRepoPath();
    if (!repoPath) {
      this._post(
        'agentMessage',
        'No workspace folder is open. Open the repo you want the assistant to work on and try again.'
      );
      return;
    }

    this._post('agentThinking', true);
    try {
      const reply = await sendMessageToAgent(trimmed, this._threadId, repoPath);
      this._post('agentMessage', reply);
    } catch (err) {
      const text = err instanceof AgentApiError ? err.message : `Unexpected error: ${(err as Error).message}`;
      this._post('agentMessage', `⚠️ ${text}`);
    } finally {
      this._post('agentThinking', false);
    }
  }

  private _getRepoPath(): string | undefined {
    const folders = vscode.workspace.workspaceFolders;
    return folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
  }

  private _post(type: string, value: unknown): void {
    this._view?.webview.postMessage({ type, value });
  }

  private _getHtml(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, 'media', 'main.js'));
    const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, 'media', 'main.css'));
    const nonce = getNonce();

    return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta
    http-equiv="Content-Security-Policy"
    content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';"
  />
  <link href="${styleUri}" rel="stylesheet" />
  <title>AI Coding Assistant</title>
</head>
<body>
  <div id="toolbar">
    <button id="new-session-btn" title="Start a new conversation">New session</button>
  </div>
  <div id="chat-log"></div>
  <div id="input-row">
    <textarea id="message-input" rows="2" placeholder="Describe a bug to fix or a feature to add…"></textarea>
    <button id="send-btn">Send</button>
  </div>
  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }
}

function getNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let text = '';
  for (let i = 0; i < 32; i++) {
    text += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return text;
}
