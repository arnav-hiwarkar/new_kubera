/* =====================================================================
   audit-engagement.js — Engagement dashboard overview
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Engagement Dashboard';
  const PAGE_URL = '/audit/engagement.html';

  const PIPELINE_STEPS = [
    { key: 'Active',                   label: 'Active',           url: '/audit/engagement.html' },
    { key: 'Trial Balance Imported',   label: 'Import TB',        url: '/audit/trial-balance.html' },
    { key: 'Mapping Complete',         label: 'Map Ledgers',      url: '/audit/mapping.html' },
    { key: 'Entries In Progress',      label: 'Entries',          url: '/audit/entries.html' },
    { key: 'Adjusted TB Approved',     label: 'Adjusted TB',      url: '/audit/adjusted-tb.html' },
    { key: 'Financials Approved',      label: 'Financials',       url: '/audit/financials.html' },
    { key: 'Report Generated',         label: 'Report',           url: '/audit/report.html' },
  ];

  let engagement = null;
  let engagementId = null;

  document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    engagementId = urlParams.get('id');

    if (!engagementId) {
      alert('No engagement ID specified.');
      window.location.href = '/audit/index.html';
      return;
    }

    window.AE.initTopbar({ showBack: true, backHref: '/audit/index.html' });
    window.AE.initSidebar(PAGE_KEY);
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, `${PAGE_URL}?id=${engagementId}`);

    // Update subnav links with ID
    const subnav = document.getElementById('audit-subnav');
    if (subnav) {
      subnav.querySelectorAll('a').forEach(link => {
        const page = link.getAttribute('href').split('?')[0];
        link.setAttribute('href', `${page}?id=${engagementId}`);
      });
    }

    await loadEngagementDetails();
  });

  async function loadEngagementDetails() {
    try {
      // 1. Fetch engagement details
      const engRes = await window.AE.apiFetch(`/api/audit/engagements/${engagementId}`);
      if (!engRes.ok) {
        if (engRes.status === 401) {
          window.AE.showAuthGuard();
          return;
        }
        showError('Engagement not found.');
        return;
      }
      engagement = await engRes.json();

      // 2. Fetch entries to count pending review
      let pendingReviewCount = 0;
      try {
        const entriesRes = await window.AE.apiFetch(`/api/audit/${engagementId}/entries`);
        if (entriesRes.ok) {
          const entries = await entriesRes.json();
          pendingReviewCount = entries.filter(e => e.status === 'Submitted').length;
        }
      } catch (err) {
        console.error('Failed to load entries count:', err);
      }

      let openQueriesCount = 0;
      try {
        const qRes = await window.AE.apiFetch(`/api/audit/${engagementId}/queries`);
        if (qRes.ok) {
          const qs = await qRes.json();
          openQueriesCount = qs.filter(q => q.status === 'Open').length;
        }
      } catch(e) { /* silent */ }

      renderHeader();
      renderPipeline();
      renderStats(pendingReviewCount, openQueriesCount);
      renderQuickActions();
      loadAndRenderAuditors();
    } catch (e) {
      console.error(e);
      showError('Network error loading engagement details.');
    }
  }

  function getPipelineIndex(status) {
    return PIPELINE_STEPS.findIndex(s => s.key.toLowerCase() === (status || 'active').toLowerCase());
  }

  function formatDate(dStr) {
    if (!dStr) return '';
    try {
      const d = new Date(dStr);
      return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch (e) {
      return dStr;
    }
  }

  function renderHeader() {
    const header = document.getElementById('engagement-header');
    if (!header) return;

    header.innerHTML = `
      <div>
        <h1 id="engagement-title" style="margin: 0; font-size: 24px; font-weight: 700; color: var(--text-primary);">
          ${window.AE.escapeHtml(engagement.client_name)}
        </h1>
        <p id="engagement-subtitle" style="font-size:13px;color:var(--text-secondary);margin-top:4px;">
          Financial Year: <strong>${window.AE.escapeHtml(engagement.financial_year)}</strong> &middot; 
          ${formatDate(engagement.period_start)} — ${formatDate(engagement.period_end)}
        </p>
      </div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <span class="audit-status-badge badge-${getStatusBadgeClass(engagement.status)}" id="engagement-status-badge">
          ${window.AE.escapeHtml(engagement.status)}
        </span>
        <button class="btn btn-secondary" id="btn-edit-engagement" style="padding: 6px 12px; font-size: 13px;">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 4px; vertical-align: middle;"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          Edit
        </button>
      </div>
    `;

    document.getElementById('btn-edit-engagement')?.addEventListener('click', () => openEditModal(engagement));
  }

  function renderPipeline() {
    const container = document.getElementById('pipeline-container');
    if (!container) return;

    const currentIdx = getPipelineIndex(engagement.status);

    const stepsHtml = PIPELINE_STEPS.map((step, idx) => {
      const isDone = idx < currentIdx;
      const isCurrent = idx === currentIdx;

      let innerClass = 'pending';
      if (isDone) innerClass = 'done';
      else if (isCurrent) innerClass = 'current';

      const content = `
        <span class="step-num">${idx + 1}</span>
        <span class="step-label">${window.AE.escapeHtml(step.label)}</span>
      `;

      // Clickable only if done
      if (isDone) {
        return `
          <div class="pipeline-step">
            <a href="${step.url}?id=${engagementId}" class="pipeline-step-inner done" style="text-decoration: none;">
              ${content}
            </a>
          </div>
        `;
      } else {
        return `
          <div class="pipeline-step">
            <div class="pipeline-step-inner ${innerClass}">
              ${content}
            </div>
          </div>
        `;
      }
    }).join('<div class="pipeline-arrow">&rarr;</div>');

    container.innerHTML = stepsHtml;
  }

  function renderStats(pendingReviewCount, openQueriesCount = 0) {
    const container = document.getElementById('stat-cards');
    if (!container) return;

    const unmapped = engagement.ledger_count - engagement.mapped_count;
    const ledgerSub = unmapped > 0
      ? `<div class="stat-card-sub" style="color: var(--status-action); font-weight: 500;">${unmapped} unmapped</div>`
      : `<div class="stat-card-sub" style="color: var(--status-verified);">All mapped</div>`;

    const pendingSub = pendingReviewCount > 0
      ? `<div class="stat-card-sub" style="color: var(--status-action); font-weight: 500;">${pendingReviewCount} pending review</div>`
      : `<div class="stat-card-sub">No pending entries</div>`;

    const queriesSub = openQueriesCount > 0
      ? `<div class="stat-card-sub" style="color: var(--status-action); font-weight: 500;">Needs attention</div>`
      : `<div class="stat-card-sub" style="color: var(--status-verified);">All resolved</div>`;

    const statusMap = {
      'Active': 'Active',
      'Trial Balance Imported': 'TB Imported',
      'Mapping Complete': 'Mapping Done',
      'Entries In Progress': 'Entries Open',
      'Adjusted TB Approved': 'Adj TB Approved',
      'Financials Approved': 'FS Approved',
      'Report Generated': 'Report Ready'
    };
    const friendlyStatus = statusMap[engagement.status] || engagement.status;

    container.innerHTML = `
      <div class="stat-card">
        <div class="stat-card-value">${engagement.ledger_count || 0}</div>
        <div class="stat-card-label">Total Ledgers</div>
        ${ledgerSub}
      </div>
      <div class="stat-card">
        <div class="stat-card-value">${engagement.entry_count || 0}</div>
        <div class="stat-card-label">Audit Entries</div>
        ${pendingSub}
      </div>
      <div class="stat-card">
        <div class="stat-card-value">${engagement.approved_entry_count || 0}</div>
        <div class="stat-card-label">Approved Entries</div>
        <div class="stat-card-sub">Included in Adjusted TB</div>
      </div>
      <a href="/audit/queries.html?id=${engagementId}" class="stat-card" style="text-decoration: none; display: block; transition: border-color 150ms ease;">
        <div class="stat-card-value" style="color: ${openQueriesCount > 0 ? 'var(--status-action)' : 'var(--text-primary)'};">${openQueriesCount}</div>
        <div class="stat-card-label">Open Queries</div>
        ${queriesSub}
      </a>
      <div class="stat-card">
        <div class="stat-card-value" style="font-size: 20px; word-break: break-all;">${window.AE.escapeHtml(friendlyStatus)}</div>
        <div class="stat-card-label">Engagement Status</div>
        <div class="stat-card-sub">Step ${getPipelineIndex(engagement.status) + 1} of 7</div>
      </div>
    `;
  }

  function renderQuickActions() {
    const container = document.getElementById('quick-actions');
    if (!container) return;

    container.innerHTML = `
      <a href="/audit/trial-balance.html?id=${engagementId}" class="quick-action-btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        Import Trial Balance
      </a>
      <a href="/audit/mapping.html?id=${engagementId}" class="quick-action-btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M2.2 12h19.6"/><path d="M12 2.2a15.3 15.3 0 0 1 4 9.8 15.3 15.3 0 0 1-4 9.8 15.3 15.3 0 0 1-4-9.8 15.3 15.3 0 0 1 4-9.8z"/></svg>
        Manage Ledger Mapping
      </a>
      <a href="/audit/entry-form.html?id=${engagementId}" class="quick-action-btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        New Audit Entry
      </a>
      <a href="/audit/adjusted-tb.html?id=${engagementId}" class="quick-action-btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
        View Adjusted TB
      </a>
      <a href="/audit/financials.html?id=${engagementId}" class="quick-action-btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
        View Financials
      </a>
      <a href="/audit/report.html?id=${engagementId}" class="quick-action-btn">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
        Generate Reports
      </a>
    `;
  }

  function getStatusBadgeClass(status) {
    if (!status) return 'active';
    const s = status.toLowerCase();
    if (s.includes('active')) return 'active';
    if (s.includes('imported')) return 'submitted'; // amber
    if (s.includes('complete') || s.includes('approved') || s.includes('generated')) return 'approved'; // green
    if (s.includes('progress')) return 'submitted'; // amber
    return 'draft';
  }

  function openEditModal(eng) {
    let modal = document.getElementById('edit-engagement-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'edit-engagement-modal';
      modal.className = 'audit-modal';
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    modal.innerHTML = `
      <div class="audit-modal-content">
        <h3>Edit Engagement Details</h3>
        <form id="form-edit-engagement">
          <div class="form-group" style="margin-bottom:12px;">
            <label class="form-label" for="edit_client_name">Client Name</label>
            <input type="text" class="input" id="edit_client_name" name="client_name" required value="${window.AE.escapeHtml(eng.client_name)}" />
          </div>
          <div class="form-group" style="margin-bottom:12px;">
            <label class="form-label" for="edit_financial_year">Financial Year</label>
            <input type="text" class="input" id="edit_financial_year" name="financial_year" required value="${window.AE.escapeHtml(eng.financial_year)}" />
          </div>
          <div class="form-group" style="margin-bottom:12px;">
            <label class="form-label" for="edit_period_start">Period Start</label>
            <input type="date" class="input" id="edit_period_start" name="period_start" required value="${eng.period_start}" />
          </div>
          <div class="form-group" style="margin-bottom:20px;">
            <label class="form-label" for="edit_period_end">Period End</label>
            <input type="date" class="input" id="edit_period_end" name="period_end" required value="${eng.period_end}" />
          </div>
          <div style="display:flex; justify-content: flex-end; gap:12px;">
            <button type="button" class="btn btn-ghost" id="btn-edit-cancel">Cancel</button>
            <button type="submit" class="btn btn-primary">Save Changes</button>
          </div>
        </form>
      </div>
    `;

    modal.querySelector('#btn-edit-cancel').addEventListener('click', () => {
      modal.style.display = 'none';
    });

    modal.querySelector('#form-edit-engagement').addEventListener('submit', async (e) => {
      e.preventDefault();
      const updated = {
        client_name: document.getElementById('edit_client_name').value.trim(),
        financial_year: document.getElementById('edit_financial_year').value.trim(),
        period_start: document.getElementById('edit_period_start').value,
        period_end: document.getElementById('edit_period_end').value,
      };

      try {
        const res = await window.AE.apiFetch(`/api/audit/engagements/${eng.id}`, {
          method: 'PATCH',
          body: JSON.stringify(updated)
        });

        if (res.ok) {
          modal.style.display = 'none';
          await loadEngagementDetails();
        } else {
          alert('Failed to update engagement.');
        }
      } catch (err) {
        console.error(err);
        alert('Network error updating engagement.');
      }
    });
  }

  function showError(msg) {
    const content = document.getElementById('main-content');
    if (content) {
      content.innerHTML = `
        <div class="stat-card" style="border-color: var(--status-action); text-align: center; padding: 24px;">
          <div style="color: var(--status-action); font-weight: 500;">${window.AE.escapeHtml(msg)}</div>
          <a href="/audit/index.html" class="btn btn-secondary" style="margin-top:12px; display:inline-block;">&larr; Back to Engagements</a>
        </div>
      `;
    }
  }



  async function loadAndRenderAuditors() {
    const container = document.getElementById('auditors-container');
    const manageBtn = document.getElementById('btn-manage-auditors');
    if (!container) return;

    try {
      const res = await window.AE.apiFetch(`/api/audit/engagements/${engagementId}/auditors`);
      if (!res.ok) throw new Error();
      const auditors = await res.json();

      if (auditors.length === 0) {
        container.innerHTML = '<span style="color:var(--text-muted);font-size:13px;font-style:italic;">No auditors assigned yet.</span>';
      } else {
        container.innerHTML = auditors.map(a => `
          <div style="display:inline-flex;align-items:center;gap:6px;background:var(--bg-raised);border:1px solid var(--border);border-radius:20px;padding:4px 12px;">
            <div style="width:22px;height:22px;border-radius:50%;background:var(--accent);color:#fff;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;">
              ${window.AE.escapeHtml(a.name.slice(0,1).toUpperCase())}
            </div>
            <span style="font-size:13px;font-weight:500;color:var(--text-primary);">${window.AE.escapeHtml(a.name)}</span>
          </div>
        `).join('');
      }
    } catch(e) {
      if (container) container.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">Could not load auditors.</span>';
    }

    manageBtn?.addEventListener('click', () => openManageAuditorsModal());
  }

  async function openManageAuditorsModal() {
    let modal = document.getElementById('manage-auditors-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'manage-auditors-modal';
      modal.className = 'audit-modal';
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    modal.innerHTML = `
      <div class="audit-modal-content" style="max-width:440px;width:95%;">
        <h3 style="margin-bottom:4px;">Manage Auditors</h3>
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;">Select auditors to assign to this engagement.</p>
        <div id="manage-auditors-list" style="max-height:280px;overflow-y:auto;display:flex;flex-direction:column;gap:4px;">
          <span style="color:var(--text-muted);font-size:13px;">Loading…</span>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:20px;">
          <button type="button" class="btn btn-ghost" id="btn-auditors-cancel">Cancel</button>
          <button type="button" class="btn btn-primary" id="btn-auditors-save">Save Changes</button>
        </div>
      </div>
    `;

    modal.querySelector('#btn-auditors-cancel').addEventListener('click', () => { modal.style.display = 'none'; });

    try {
      const [allRes, assignedRes] = await Promise.all([
        window.AE.apiFetch('/api/users/auditors'),
        window.AE.apiFetch(`/api/audit/engagements/${engagementId}/auditors`)
      ]);
      const all = allRes.ok ? await allRes.json() : [];
      const assigned = assignedRes.ok ? await assignedRes.json() : [];
      const assignedIds = new Set(assigned.map(a => a.user_id));

      const listEl = document.getElementById('manage-auditors-list');
      if (all.length === 0) {
        listEl.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">No auditors in system.</span>';
        return;
      }
      listEl.innerHTML = all.map(a => `
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px 10px;border-radius:6px;background:var(--bg-raised);">
          <input type="checkbox" name="manage_auditor" value="${a.id}" ${assignedIds.has(a.id) ? 'checked' : ''} style="width:16px;height:16px;accent-color:var(--accent);" />
          <div style="width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
            ${window.AE.escapeHtml(a.name.slice(0,1).toUpperCase())}
          </div>
          <div>
            <div style="font-size:13px;font-weight:500;color:var(--text-primary);">${window.AE.escapeHtml(a.name)}</div>
            <div style="font-size:11px;color:var(--text-muted);">@${window.AE.escapeHtml(a.username)}</div>
          </div>
        </label>
      `).join('');
    } catch(e) {
      const listEl = document.getElementById('manage-auditors-list');
      if (listEl) listEl.innerHTML = '<span style="color:var(--status-action);font-size:13px;">Failed to load auditors.</span>';
    }

    modal.querySelector('#btn-auditors-save').addEventListener('click', async () => {
      const checked = Array.from(modal.querySelectorAll('input[name="manage_auditor"]:checked'))
        .map(el => parseInt(el.value, 10));
      try {
        await window.AE.apiFetch(`/api/audit/engagements/${engagementId}/auditors`, {
          method: 'POST',
          body: JSON.stringify({ user_ids: checked })
        });
        modal.style.display = 'none';
        await loadAndRenderAuditors();
      } catch(e) {
        alert('Failed to save auditor assignments.');
      }
    });
  }
})();
