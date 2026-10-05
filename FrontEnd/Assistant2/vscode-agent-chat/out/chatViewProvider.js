"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ChatViewProvider = void 0;
const vscode = __importStar(require("vscode"));
const crypto_1 = require("crypto");
const agentClient_1 = require("./agentClient");
/**
 * Webview sidebar that lets the user chat with the Agent2.py backend.
 * Every user message is sent with the current thread_id and the
 * workspace's repo_path; the AI reply is streamed back into the panel.
 */
class ChatViewProvider {
    constructor(_extensionUri) {
        this._extensionUri = _extensionUri;
        this._threadId = (0, crypto_1.randomUUID)();
    }
    resolveWebviewView(webviewView, _context, _token) {
        this._view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [vscode.Uri.joinPath(this._extensionUri, 'media')],
        };
        webviewView.webview.html = this._getHtml(webviewView.webview);
        webviewView.webview.onDidReceiveMessage(async (msg) => {
            switch (msg.type) {
                case 'userMessage':
                    await this._handleUserMessage(msg.value ?? '');
                    break;
                case 'newSession':
                    this._threadId = (0, crypto_1.randomUUID)();
                    this._post('sessionReset', this._threadId);
                    break;
            }
        });
    }
    /** Called from a command palette entry / button to start a fresh thread. */
    startNewSession() {
        this._threadId = (0, crypto_1.randomUUID)();
        this._post('sessionReset', this._threadId);
    }
    async _handleUserMessage(message) {
        const trimmed = message.trim();
        if (!trimmed) {
            return;
        }
        const repoPath = this._getRepoPath();
        if (!repoPath) {
            this._post('agentMessage', 'No workspace folder is open. Open the repo you want the assistant to work on and try again.');
            return;
        }
        this._post('agentThinking', true);
        try {
            const reply = await (0, agentClient_1.sendMessageToAgent)(trimmed, this._threadId, repoPath);
            this._post('agentMessage', reply);
        }
        catch (err) {
            const text = err instanceof agentClient_1.AgentApiError ? err.message : `Unexpected error: ${err.message}`;
            this._post('agentMessage', `⚠️ ${text}`);
        }
        finally {
            this._post('agentThinking', false);
        }
    }
    _getRepoPath() {
        const folders = vscode.workspace.workspaceFolders;
        return folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
    }
    _post(type, value) {
        this._view?.webview.postMessage({ type, value });
    }
    _getHtml(webview) {
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
exports.ChatViewProvider = ChatViewProvider;
ChatViewProvider.viewType = 'aiCodingAssistant.chatView';
function getNonce() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let text = '';
    for (let i = 0; i < 32; i++) {
        text += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return text;
}
//# sourceMappingURL=chatViewProvider.js.map