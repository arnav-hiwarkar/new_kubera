/* =====================================================================
   audit-queries.js — Queries tab logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Queries';
  const PAGE_URL = '/audit/queries.html';

  let engagementId = null;
  let currentUser = null;
  let allQueries = [];
  let currentQueryId = null;

  document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    engagementId = urlParams.get('id');

    if (!engagementId) {
      alert('No engagement ID specified.');
      window.location.href = '/audit/index.html';
      return;
    }

    window.AE.initTopbar({ showBack: true, backHref: `/audit/engagement.html?id=${engagementId}` });
    window.AE.initSidebar(PAGE_KEY);
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, `${PAGE_URL}?id=${engagementId}`);

    // Update subnav links with ?id=
    const subnav = document.getElementById('audit-subnav');
    if (subnav) {
      subnav.querySelectorAll('a').forEach(link => {
        const page = link.getAttribute('href').split('?')[0];
        link.setAttribute('href', `${page}?id=${engagementId}`);
      });
    }

    // Get current user
    currentUser = window.AE.getCurrentUser();

    document.getElementById('btn-new-query')?.addEventListener('click', openNewQueryModal);

    await loadQueries();
  });

  // ── Load & Render Query List ──────────────────────────────────────

  async function loadQueries(selectId = null) {
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/queries`);
      if (!res.ok) throw new Error();
      allQueries = await res.json();
      renderQueryList();

      // Auto-select: if selectId given use it, else keep currentQueryId, else select first
      const idToSelect = selectId || currentQueryId || (allQueries.length > 0 ? allQueries[0].id : null);
      if (idToSelect) {
        await loadQueryThread(idToSelect);
      } else {
        showEmptyThread();
      }
    } catch (e) {
      console.error(e);
      document.getElementById('queries-list-body').innerHTML =
        '<div style="padding:24px;text-align:center;color:var(--status-action);font-size:13px;">Failed to load queries.</div>';
    }
  }

  function renderQueryList() {
    const body = document.getElementById('queries-list-body');
    const countEl = document.getElementById('queries-count');
    if (!body) return;

    const openCount = allQueries.filter(q => q.status === 'Open').length;
    if (countEl) {
      countEl.textContent = `${allQueries.length} total · ${openCount} open`;
    }

    if (allQueries.length === 0) {
      body.innerHTML = `
        <div style="padding:48px 24px;text-align:center;">
          <div style="color:var(--text-muted);font-size:13px;">No queries yet.<br/>Click "+ New Query" to raise the first one.</div>
        </div>
      `;
      return;
    }

    body.innerHTML = allQueries.map(q => {
      const isActive = q.id === currentQueryId;
      const isOpen = q.status === 'Open';
      const statusClass = isOpen ? 'query-status-open' : (q.status === 'Resolved' ? 'query-status-resolved' : 'query-status-closed');
      const lastActivity = q.last_reply_at || q.created_at;
      return `
        <div class="query-card ${isActive ? 'active' : ''}" data-id="${q.id}">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;">
            <span class="query-type-badge">${window.AE.escapeHtml(q.query_type)}</span>
            <span class="query-status-badge ${statusClass}">${window.AE.escapeHtml(q.status)}</span>
          </div>
          <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:4px;line-height:1.3;">
            ${window.AE.escapeHtml(q.subject)}
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;">
            <span style="font-size:11px;color:var(--text-muted);">
              by ${window.AE.escapeHtml(q.raised_by_name)}
            </span>
            <div style="display:flex;align-items:center;gap:8px;">
              ${q.reply_count > 0 ? `<span style="font-size:11px;color:var(--text-muted);">${q.reply_count} ${q.reply_count === 1 ? 'reply' : 'replies'}</span>` : ''}
              <span style="font-size:11px;color:var(--text-muted);">${formatRelativeTime(lastActivity)}</span>
            </div>
          </div>
        </div>
      `;
    }).join('');

    body.querySelectorAll('.query-card').forEach(card => {
      card.addEventListener('click', () => {
        const id = parseInt(card.dataset.id);
        loadQueryThread(id);
      });
    });
  }

  // ── Load & Render Thread ──────────────────────────────────────────

  async function loadQueryThread(queryId) {
    currentQueryId = queryId;

    // Update active state in list
    document.querySelectorAll('.query-card').forEach(c => {
      c.classList.toggle('active', parseInt(c.dataset.id) === queryId);
    });

    const right = document.getElementById('queries-right');
    if (!right) return;

    right.innerHTML = '<div style="flex:1;display:flex;align-items:center;justify-content:center;"><span class="spinner"></span></div>';

    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/queries/${queryId}`);
      if (!res.ok) throw new Error();
      const query = await res.json();
      renderThread(query);
    } catch (e) {
      right.innerHTML = '<div style="padding:32px;text-align:center;color:var(--status-action);font-size:13px;">Failed to load thread.</div>';
    }
  }

  function renderThread(query) {
    const right = document.getElementById('queries-right');
    if (!right) return;

    const isOpen = query.status === 'Open';
    const isClosed = query.status === 'Closed';
    const statusClass = isOpen ? 'query-status-open' : (query.status === 'Resolved' ? 'query-status-resolved' : 'query-status-closed');
    const isAuditor = currentUser && currentUser.role === 'auditor';

    const repliesHtml = query.replies.length === 0
      ? `<div style="flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:13px;font-style:italic;">No replies yet. Be the first to respond.</div>`
      : query.replies.map(r => renderReply(r)).join('');

    right.innerHTML = `
      <div class="thread-header">
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap;">
            <span class="query-type-badge">${window.AE.escapeHtml(query.query_type)}</span>
            <span class="query-status-badge ${statusClass}">${window.AE.escapeHtml(query.status)}</span>
          </div>
          <h2 style="font-size:16px;font-weight:700;color:var(--text-primary);margin:0;line-height:1.3;">${window.AE.escapeHtml(query.subject)}</h2>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">
            Raised by <strong>${window.AE.escapeHtml(query.raised_by_name)}</strong> · ${formatDate(query.created_at)}
          </div>
        </div>
        <div style="flex-shrink:0; display:flex; gap:8px;">
          ${!isClosed ? `<button class="btn btn-ghost" id="btn-close" style="font-size:12px;padding:6px 14px;border:1px solid var(--border);">Close</button>` : ''}
          ${isAuditor && isOpen ? `<button class="btn btn-secondary" id="btn-resolve" style="font-size:12px;padding:6px 14px;">Mark Resolved</button>` : ''}
          ${isAuditor && !isOpen ? `<button class="btn btn-secondary" id="btn-reopen" style="font-size:12px;padding:6px 14px;">Reopen</button>` : ''}
        </div>
      </div>

      ${query.description ? `
        <div class="thread-description">
          <p style="font-size:13px;color:var(--text-secondary);line-height:1.6;margin:0;">${window.AE.escapeHtml(query.description)}</p>
        </div>
      ` : ''}

      <div class="thread-replies" id="thread-replies">
        ${repliesHtml}
      </div>

      <div class="thread-composer" id="thread-composer">
        <div class="composer-inner">
          <div style="display:flex;align-items:flex-start;gap:10px;width:100%;">
            <div style="width:32px;height:32px;border-radius:50%;background:var(--accent);color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px;">
              ${currentUser ? window.AE.escapeHtml(currentUser.name.slice(0,1).toUpperCase()) : '?'}
            </div>
            <div style="flex:1;min-width:0;">
              <textarea id="reply-text" placeholder="${isOpen ? 'Write a reply…' : (isClosed ? 'This query is closed.' : 'This query is resolved. Reopen to reply.')}" rows="3" 
                style="width:100%;resize:vertical;min-height:72px;border-radius:6px;border:1px solid var(--border);background:var(--bg-surface);color:var(--text-primary);padding:10px 12px;font-size:13px;font-family:inherit;line-height:1.5;"
                ${!isOpen ? 'disabled' : ''}></textarea>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px;">
                <label style="display:flex;align-items:center;gap:6px;cursor:${!isOpen ? 'not-allowed' : 'pointer'};opacity:${!isOpen ? '0.5' : '1'};">
                  <input type="file" id="reply-file" style="display:none;" ${!isOpen ? 'disabled' : ''} />
                  <button type="button" id="btn-pick-file" class="btn btn-ghost" style="padding:5px 10px;font-size:12px;" ${!isOpen ? 'disabled' : ''}>
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                    Attach file
                  </button>
                  <span id="reply-filename" style="font-size:12px;color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></span>
                </label>
                <button class="btn btn-primary" id="btn-send-reply" style="padding:7px 18px;font-size:13px;" ${!isOpen ? 'disabled' : ''}>Send Reply</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    `;

    // File picker
    right.querySelector('#btn-pick-file')?.addEventListener('click', () => {
      right.querySelector('#reply-file')?.click();
    });
    right.querySelector('#reply-file')?.addEventListener('change', (e) => {
      const file = e.target.files[0];
      const nameEl = right.querySelector('#reply-filename');
      if (nameEl) nameEl.textContent = file ? file.name : '';
    });

    // Send reply
    right.querySelector('#btn-send-reply')?.addEventListener('click', () => sendReply(query.id));

    // Resolve / Reopen / Close
    right.querySelector('#btn-close')?.addEventListener('click', () => closeQuery(query.id));
    right.querySelector('#btn-resolve')?.addEventListener('click', () => resolveQuery(query.id));
    right.querySelector('#btn-reopen')?.addEventListener('click', () => reopenQuery(query.id));

    // Scroll replies to bottom
    const repliesEl = document.getElementById('thread-replies');
    if (repliesEl) repliesEl.scrollTop = repliesEl.scrollHeight;
  }

  function renderReply(reply) {
    const isAuditor = reply.sent_by_role === 'auditor';
    return `
      <div class="reply-bubble ${isAuditor ? 'reply-auditor' : 'reply-company'}">
        <div class="reply-meta">
          <div style="display:flex;align-items:center;gap:6px;">
            <div style="width:24px;height:24px;border-radius:50%;background:${isAuditor ? 'var(--accent)' : 'var(--status-verified)'};color:#fff;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
              ${window.AE.escapeHtml(reply.sent_by_name.slice(0,1).toUpperCase())}
            </div>
            <strong style="font-size:13px;color:var(--text-primary);">${window.AE.escapeHtml(reply.sent_by_name)}</strong>
            <span class="reply-role-tag ${isAuditor ? 'reply-role-auditor' : 'reply-role-company'}">${isAuditor ? 'Auditor' : 'Company'}</span>
          </div>
          <span style="font-size:11px;color:var(--text-muted);">${formatDate(reply.created_at)}</span>
        </div>
        ${reply.message ? `<div style="font-size:13px;color:var(--text-primary);line-height:1.6;white-space:pre-wrap;margin-top:6px;">${window.AE.escapeHtml(reply.message)}</div>` : ''}
        ${reply.download_url ? `
          <a href="${reply.download_url}" class="reply-attachment" download="${window.AE.escapeHtml(reply.original_filename || 'attachment')}">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            ${window.AE.escapeHtml(reply.original_filename || 'Download attachment')}
          </a>
        ` : ''}
      </div>
    `;
  }

  function showEmptyThread() {
    const right = document.getElementById('queries-right');
    if (right) {
      right.innerHTML = `
        <div class="queries-empty-state">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <p>Select a query to view the conversation thread</p>
        </div>
      `;
    }
  }

  // ── Actions ────────────────────────────────────────────────────────

  async function sendReply(queryId) {
    const textEl = document.getElementById('reply-text');
    const fileEl = document.getElementById('reply-file');
    const btn = document.getElementById('btn-send-reply');

    const message = (textEl?.value || '').trim();
    const file = fileEl?.files?.[0];

    if (!message && !file) {
      alert('Please enter a message or attach a file before sending.');
      return;
    }

    if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }

    try {
      const formData = new FormData();
      if (message) formData.append('message', message);
      if (file) formData.append('file', file);

      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/queries/${queryId}/replies`, {
        method: 'POST',
        body: formData
      });

      if (res.ok) {
        await loadQueries(queryId);
      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.error || 'Failed to send reply.');
        if (btn) { btn.disabled = false; btn.textContent = 'Send Reply'; }
      }
    } catch (e) {
      alert('Network error sending reply.');
      if (btn) { btn.disabled = false; btn.textContent = 'Send Reply'; }
    }
  }

  async function resolveQuery(queryId) {
    if (!confirm('Mark this query as Resolved?')) return;
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/queries/${queryId}/resolve`, { method: 'PATCH' });
      if (res.ok) await loadQueries(queryId);
      else { const e = await res.json().catch(()=>({})); alert(e.error || 'Failed to resolve.'); }
    } catch (e) { alert('Network error.'); }
  }

  async function closeQuery(queryId) {
    if (!confirm('Close this query? It will be marked as closed.')) return;
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/queries/${queryId}/close`, { method: 'PATCH' });
      if (res.ok) await loadQueries(queryId);
      else { const e = await res.json().catch(()=>({})); alert(e.error || 'Failed to close.'); }
    } catch (e) { alert('Network error.'); }
  }

  async function reopenQuery(queryId) {
    if (!confirm('Reopen this query?')) return;
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/queries/${queryId}/reopen`, { method: 'PATCH' });
      if (res.ok) await loadQueries(queryId);
      else { const e = await res.json().catch(()=>({})); alert(e.error || 'Failed to reopen.'); }
    } catch (e) { alert('Network error.'); }
  }

  // ── New Query Modal ────────────────────────────────────────────────

  function openNewQueryModal() {
    let modal = document.getElementById('new-query-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'new-query-modal';
      modal.className = 'audit-modal';
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    modal.innerHTML = `
      <div class="audit-modal-content" style="max-width:480px;width:95%;">
        <h3 style="margin-bottom:4px;">Raise a New Query</h3>
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;">Ask a question or request documents from the client.</p>
        <div class="form-group" style="margin-bottom:14px;">
          <label class="form-label" for="nq-type">Query Type</label>
          <select class="input" id="nq-type">
            <option value="General">General</option>
            <option value="Document Request">Document Request</option>
            <option value="Clarification">Clarification</option>
            <option value="Observation">Observation</option>
          </select>
        </div>
        <div class="form-group" style="margin-bottom:14px;">
          <label class="form-label" for="nq-subject">Subject *</label>
          <input type="text" class="input" id="nq-subject" placeholder="Brief description of the query" />
        </div>
        <div class="form-group" style="margin-bottom:20px;">
          <label class="form-label" for="nq-description">Details <span style="font-weight:400;color:var(--text-muted);">(optional)</span></label>
          <textarea class="input" id="nq-description" rows="3" placeholder="Provide any additional context or details…" style="resize:vertical;min-height:72px;line-height:1.5;"></textarea>
        </div>
        <div id="nq-error" style="font-size:12px;color:var(--status-action);min-height:18px;margin-bottom:8px;"></div>
        <div style="display:flex;justify-content:flex-end;gap:12px;">
          <button type="button" class="btn btn-ghost" id="nq-cancel">Cancel</button>
          <button type="button" class="btn btn-primary" id="nq-submit">Raise Query</button>
        </div>
      </div>
    `;

    modal.querySelector('#nq-cancel').addEventListener('click', () => { modal.style.display = 'none'; });
    modal.querySelector('#nq-subject').focus();

    modal.querySelector('#nq-submit').addEventListener('click', async () => {
      const type = modal.querySelector('#nq-type').value;
      const subject = modal.querySelector('#nq-subject').value.trim();
      const description = modal.querySelector('#nq-description').value.trim();
      const errEl = modal.querySelector('#nq-error');
      const btn = modal.querySelector('#nq-submit');

      if (!subject) { errEl.textContent = 'Subject is required.'; return; }
      errEl.textContent = '';
      btn.disabled = true;
      btn.textContent = 'Creating…';

      try {
        const res = await window.AE.apiFetch(`/api/audit/${engagementId}/queries`, {
          method: 'POST',
          body: JSON.stringify({ query_type: type, subject, description: description || null })
        });
        if (res.ok) {
          const newQuery = await res.json();
          modal.style.display = 'none';
          await loadQueries(newQuery.id);
        } else {
          const err = await res.json().catch(() => ({}));
          errEl.textContent = err.error || 'Failed to create query.';
          btn.disabled = false;
          btn.textContent = 'Raise Query';
        }
      } catch (e) {
        errEl.textContent = 'Network error. Please try again.';
        btn.disabled = false;
        btn.textContent = 'Raise Query';
      }
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────

  function formatDate(str) {
    if (!str) return '';
    try {
      return new Date(str).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      });
    } catch (e) { return str; }
  }

  function formatRelativeTime(str) {
    if (!str) return '';
    try {
      const diff = Date.now() - new Date(str).getTime();
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return 'just now';
      if (mins < 60) return `${mins}m ago`;
      const hrs = Math.floor(mins / 60);
      if (hrs < 24) return `${hrs}h ago`;
      const days = Math.floor(hrs / 24);
      return `${days}d ago`;
    } catch (e) { return ''; }
  }

})();
