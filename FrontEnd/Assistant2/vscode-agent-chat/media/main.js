// @ts-nocheck
(function () {
  const vscode = acquireVsCodeApi();

  const chatLog = document.getElementById('chat-log');
  const input = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const newSessionBtn = document.getElementById('new-session-btn');

  // ── Minimal markdown formatting ────────────────────────────────────
  function formatMarkdown(text) {
    return text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`([^`]+)`/g, '<code>$1</code>');
  }

  // ── Parse a unified diff string into structured lines ──────────────
  function parseDiffLines(diffText) {
    const lines = diffText.split('\n');
    const result = [];
    let lineNum = 0;

    for (const line of lines) {
      if (line.startsWith('@@')) {
        // Extract line number from hunk header
        const match = line.match(/@@ [^+]*\+(\d+)/);
        if (match) {
          lineNum = parseInt(match[1], 10) - 1;
        }
        result.push({ type: 'hunk-header', text: line, num: '' });
      } else if (line.startsWith('+++') || line.startsWith('---')) {
        // Skip file header lines in display
        continue;
      } else if (line.startsWith('+')) {
        lineNum++;
        result.push({ type: 'added', text: line.substring(1), num: lineNum });
      } else if (line.startsWith('-')) {
        result.push({ type: 'removed', text: line.substring(1), num: '' });
      } else if (line.startsWith('diff ') || line.startsWith('index ')) {
        // Skip meta lines
        continue;
      } else {
        lineNum++;
        result.push({ type: 'context', text: line.replace(/^ /, ''), num: lineNum });
      }
    }
    return result;
  }

  // ── Render a diff block (reused by both diff-review and approval) ──
  function renderDiffBlock(diffText) {
    const container = document.createElement('div');
    container.className = 'diff-content';

    const lines = parseDiffLines(diffText);
    for (const line of lines) {
      const lineEl = document.createElement('div');
      lineEl.className = `diff-line ${line.type}`;

      const numSpan = document.createElement('span');
      numSpan.className = 'diff-line-num';
      numSpan.textContent = line.num !== '' ? String(line.num) : '';

      const textSpan = document.createElement('span');
      textSpan.className = 'diff-line-text';
      const prefix = line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' ';
      textSpan.textContent = (line.type === 'hunk-header' ? '' : prefix) + line.text;

      lineEl.appendChild(numSpan);
      lineEl.appendChild(textSpan);
      container.appendChild(lineEl);
    }

    return container;
  }

  // ── Count additions/deletions in a diff ────────────────────────────
  function countDiffStats(diffText) {
    const lines = diffText.split('\n');
    let additions = 0;
    let deletions = 0;
    for (const line of lines) {
      if (line.startsWith('+') && !line.startsWith('+++')) { additions++; }
      if (line.startsWith('-') && !line.startsWith('---')) { deletions++; }
    }
    return { additions, deletions };
  }

  // ── Try to detect & render a diff-review block ─────────────────────
  function tryRenderDiffReview(text) {
    const pattern = /```diff-review\n([\s\S]*?)```/;
    const match = text.match(pattern);
    if (!match) { return null; }

    let files;
    try {
      files = JSON.parse(match[1]);
    } catch {
      return null;
    }

    if (!Array.isArray(files) || files.length === 0) { return null; }

    // Extract the header text (everything before the fenced block)
    const headerText = text.substring(0, text.indexOf('```diff-review')).trim();

    // Build the DOM
    const wrapper = document.createElement('div');

    // Header paragraph
    if (headerText) {
      const headerEl = document.createElement('div');
      headerEl.style.marginBottom = '12px';
      headerEl.innerHTML = formatMarkdown(headerText);
      wrapper.appendChild(headerEl);
    }

    const container = document.createElement('div');
    container.className = 'diff-review-container';

    // Track per-file decisions
    const decisions = {};
    files.forEach(f => { decisions[f.file] = null; });

    // ── Bulk actions ────────────────────────────────────────────────
    const bulkBar = document.createElement('div');
    bulkBar.className = 'diff-bulk-actions';

    const acceptAllBtn = document.createElement('button');
    acceptAllBtn.className = 'diff-bulk-btn accept-all';
    acceptAllBtn.textContent = '✓  Accept All';

    const declineAllBtn = document.createElement('button');
    declineAllBtn.className = 'diff-bulk-btn decline-all';
    declineAllBtn.textContent = '✗  Decline All';

    bulkBar.appendChild(acceptAllBtn);
    bulkBar.appendChild(declineAllBtn);
    container.appendChild(bulkBar);

    // ── Per-file cards ──────────────────────────────────────────────
    const cards = [];

    files.forEach((fileData, idx) => {
      const card = document.createElement('div');
      card.className = 'diff-file-card';
      card.dataset.file = fileData.file;

      const diff = fileData.diff || fileData.patch || '';
      const stats = countDiffStats(diff);

      // Header
      const header = document.createElement('div');
      header.className = 'diff-file-header';

      const chevron = document.createElement('span');
      chevron.className = 'diff-file-chevron';
      chevron.textContent = '▼';

      const name = document.createElement('span');
      name.className = 'diff-file-name';
      name.textContent = fileData.file;

      const statsEl = document.createElement('span');
      statsEl.className = 'diff-stats';
      statsEl.innerHTML =
        `<span class="additions">+${stats.additions}</span>` +
        `<span class="deletions">−${stats.deletions}</span>`;

      const badge = document.createElement('span');
      badge.className = 'diff-file-badge pending';
      badge.textContent = 'pending';

      header.appendChild(chevron);
      header.appendChild(name);
      header.appendChild(statsEl);
      header.appendChild(badge);
      card.appendChild(header);

      // Body
      const body = document.createElement('div');
      body.className = 'diff-file-body';

      if (diff) {
        body.appendChild(renderDiffBlock(diff));
      } else {
        const noContent = document.createElement('div');
        noContent.style.padding = '14px';
        noContent.style.color = 'var(--vscode-descriptionForeground)';
        noContent.textContent = 'No diff content available.';
        body.appendChild(noContent);
      }

      // Actions
      const actions = document.createElement('div');
      actions.className = 'diff-file-actions';

      const acceptBtn = document.createElement('button');
      acceptBtn.className = 'diff-action-btn accept';
      acceptBtn.textContent = '✓  Accept';

      const declineBtn = document.createElement('button');
      declineBtn.className = 'diff-action-btn decline';
      declineBtn.textContent = '✗  Decline';

      actions.appendChild(acceptBtn);
      actions.appendChild(declineBtn);
      body.appendChild(actions);
      card.appendChild(body);

      // Collapse toggle
      header.addEventListener('click', () => {
        body.classList.toggle('collapsed');
        chevron.classList.toggle('collapsed');
      });

      // Per-file accept
      acceptBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        decisions[fileData.file] = 'accepted';
        card.className = 'diff-file-card accepted';
        badge.className = 'diff-file-badge accepted-badge';
        badge.textContent = 'accepted';
        acceptBtn.disabled = true;
        declineBtn.disabled = false;
      });

      // Per-file decline
      declineBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        decisions[fileData.file] = 'declined';
        card.className = 'diff-file-card declined';
        badge.className = 'diff-file-badge declined-badge';
        badge.textContent = 'declined';
        declineBtn.disabled = true;
        acceptBtn.disabled = false;
      });

      cards.push({ card, acceptBtn, declineBtn, badge });
      container.appendChild(card);
    });

    // Bulk accept handler
    acceptAllBtn.addEventListener('click', () => {
      cards.forEach(({ card, acceptBtn, declineBtn, badge }) => {
        const filePath = card.dataset.file;
        decisions[filePath] = 'accepted';
        card.className = 'diff-file-card accepted';
        badge.className = 'diff-file-badge accepted-badge';
        badge.textContent = 'accepted';
        acceptBtn.disabled = true;
        declineBtn.disabled = false;
      });
      submitDecisions();
    });

    // Bulk decline handler
    declineAllBtn.addEventListener('click', () => {
      cards.forEach(({ card, acceptBtn, declineBtn, badge }) => {
        const filePath = card.dataset.file;
        decisions[filePath] = 'declined';
        card.className = 'diff-file-card declined';
        badge.className = 'diff-file-badge declined-badge';
        badge.textContent = 'declined';
        declineBtn.disabled = true;
        acceptBtn.disabled = false;
      });
      submitDecisions();
    });

    // ── Submit button (when using per-file selections) ──────────────
    const submitRow = document.createElement('div');
    submitRow.style.marginTop = '8px';

    const submitBtn = document.createElement('button');
    submitBtn.className = 'diff-bulk-btn accept-all';
    submitBtn.style.width = '100%';
    submitBtn.textContent = 'Submit Selections';
    submitBtn.addEventListener('click', submitDecisions);
    submitRow.appendChild(submitBtn);
    container.appendChild(submitRow);

    function submitDecisions() {
      const accepted = [];
      const declined = [];
      for (const [path, decision] of Object.entries(decisions)) {
        if (decision === 'accepted') { accepted.push(path); }
        else { declined.push(path); }
      }

      // Send structured JSON reply
      const payload = JSON.stringify({ accepted_files: accepted, declined_files: declined });
      vscode.postMessage({ type: 'userMessage', value: payload });

      // Disable all interactive elements
      bulkBar.remove();
      submitRow.remove();
      cards.forEach(({ acceptBtn, declineBtn }) => {
        acceptBtn.disabled = true;
        declineBtn.disabled = true;
      });

      // Show result banner
      const banner = document.createElement('div');
      banner.className = `diff-submitted-banner ${accepted.length > 0 ? 'success' : 'declined-banner'}`;
      banner.textContent = accepted.length > 0
        ? `✓ Submitted: ${accepted.length} accepted, ${declined.length} declined`
        : `✗ All ${declined.length} file(s) declined`;
      container.appendChild(banner);

      chatLog.scrollTop = chatLog.scrollHeight;
    }

    wrapper.appendChild(container);
    return wrapper;
  }

  // ── Try to detect & render a simple human_approval diff ────────────
  function tryRenderApproval(text) {
    // Matches: "The fix passed all tests. Here's the diff:\n\n<diff>\n\nReply 'y'..."
    const approvalPattern = /^(.*?(?:diff|changes?)[:\s]*)\n\n((?:diff --git[\s\S]+?|(?:[+-]{3} [\s\S]+?)))\n\nReply '?y/i;
    // Also try a simpler pattern
    if (!text.includes("Reply 'y' to apply") && !text.includes("Reply 'y' to proceed")) {
      return null;
    }

    // Extract diff content - look for unified diff patterns
    const diffMatch = text.match(/((?:diff --git[\s\S]*?)(?=\n\nReply)|(?:--- [\s\S]*?)(?=\n\nReply))/);
    if (!diffMatch) { return null; }

    const diffText = diffMatch[1].trim();
    if (!diffText) { return null; }

    // Extract header (text before the diff)
    const headerText = text.substring(0, text.indexOf(diffText)).trim();

    const wrapper = document.createElement('div');

    // Header
    if (headerText) {
      const headerEl = document.createElement('div');
      headerEl.style.marginBottom = '10px';
      headerEl.innerHTML = formatMarkdown(headerText);
      wrapper.appendChild(headerEl);
    }

    const container = document.createElement('div');
    container.className = 'approval-container';

    // Diff viewer
    const diffBlock = document.createElement('div');
    diffBlock.className = 'approval-diff-block';

    const diffHeader = document.createElement('div');
    diffHeader.className = 'approval-diff-header';

    const stats = countDiffStats(diffText);
    diffHeader.innerHTML =
      `Proposed Changes ` +
      `<span class="diff-stats" style="margin-left:8px">` +
      `<span class="additions">+${stats.additions}</span> ` +
      `<span class="deletions">−${stats.deletions}</span>` +
      `</span>`;

    diffBlock.appendChild(diffHeader);
    diffBlock.appendChild(renderDiffBlock(diffText));
    container.appendChild(diffBlock);

    // Approve / Reject buttons
    const actions = document.createElement('div');
    actions.className = 'approval-actions';

    const approveBtn = document.createElement('button');
    approveBtn.className = 'approval-btn approve';
    approveBtn.textContent = '✓  Approve & Apply';

    const rejectBtn = document.createElement('button');
    rejectBtn.className = 'approval-btn reject';
    rejectBtn.textContent = '✗  Discard';

    actions.appendChild(approveBtn);
    actions.appendChild(rejectBtn);
    container.appendChild(actions);

    approveBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'userMessage', value: 'y' });
      approveBtn.disabled = true;
      rejectBtn.disabled = true;

      const banner = document.createElement('div');
      banner.className = 'diff-submitted-banner success';
      banner.textContent = '✓ Changes approved — applying to workspace…';
      container.appendChild(banner);
      actions.remove();

      chatLog.scrollTop = chatLog.scrollHeight;
    });

    rejectBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'userMessage', value: 'n' });
      approveBtn.disabled = true;
      rejectBtn.disabled = true;

      const banner = document.createElement('div');
      banner.className = 'diff-submitted-banner declined-banner';
      banner.textContent = '✗ Changes discarded.';
      container.appendChild(banner);
      actions.remove();

      chatLog.scrollTop = chatLog.scrollHeight;
    });

    wrapper.appendChild(container);
    return wrapper;
  }

  // ── Append a message (with rich rendering if applicable) ───────────
  function appendMessage(sender, text) {
    const el = document.createElement('div');
    el.className = `msg ${sender}`;

    if (sender === 'agent') {
      // Try rich renderers first
      const diffReviewEl = tryRenderDiffReview(text);
      if (diffReviewEl) {
        el.appendChild(diffReviewEl);
        chatLog.appendChild(el);
        chatLog.scrollTop = chatLog.scrollHeight;
        return;
      }

      const approvalEl = tryRenderApproval(text);
      if (approvalEl) {
        el.appendChild(approvalEl);
        chatLog.appendChild(el);
        chatLog.scrollTop = chatLog.scrollHeight;
        return;
      }

      // Fallback: render with basic markdown
      el.innerHTML = formatMarkdown(text);
    } else {
      el.textContent = text;
    }

    chatLog.appendChild(el);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function setThinking(isThinking) {
    sendBtn.disabled = isThinking;
    sendBtn.textContent = isThinking ? 'Thinking…' : 'Send';
  }

  function send() {
    const text = input.value.trim();
    if (!text) {
      return;
    }
    appendMessage('user', text);
    vscode.postMessage({ type: 'userMessage', value: text });
    input.value = '';
  }

  sendBtn.addEventListener('click', send);
  newSessionBtn.addEventListener('click', () => vscode.postMessage({ type: 'newSession' }));

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  window.addEventListener('message', (event) => {
    const { type, value } = event.data;
    switch (type) {
      case 'agentMessage':
        appendMessage('agent', value);
        break;
      case 'agentThinking':
        setThinking(value);
        break;
      case 'sessionReset':
        chatLog.innerHTML = '';
        appendMessage('agent', 'Started a new session.');
        break;
    }
  });
})();
