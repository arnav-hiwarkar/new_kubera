/* =====================================================================
   doc-dashboard.js — Document Dashboard page logic
   Status summary cards + document list panel + file detail + upload modal
   ===================================================================== */

(function () {
  const PAGE_KEY = 'doc-dashboard';
  const PAGE_LABEL = 'Document Dashboard';
  const PAGE_URL = '/documents/dashboard.html';

  const CATEGORIES = {
    'Indirect Tax': ['GST Returns', 'VAT Filings', 'Customs Duty', 'Service Tax', 'Excise'],
    'Employees': ['Payroll', 'PF/ESI', 'TDS on Salary', 'Leave Records', 'Contracts'],
    'Income Tax': ['ITR Filing', 'Advance Tax', 'TDS Returns', 'Form 16', 'Tax Audit Report'],
    'Asset Management': ['Fixed Assets Register', 'Depreciation Schedules', 'Asset Purchase Invoices', 'Asset Disposal Records', 'Insurance Policies', 'Lease Agreements', 'Asset Valuation Reports'],
    'Sales Management': ['Sales Invoices', 'Customer Contracts', 'Sales Returns', 'Debtors Ledger', 'Sales Tax Returns', 'Credit Notes', 'Sales Reports']
  };

  const STATUSES = ['Uploaded', 'Pending Approval', 'Action Required', 'Verified', 'Submitted', 'Overdue'];

  const STATUS_CLASS = {
    'Uploaded': 's-uploaded',
    'Pending Approval': 's-pending',
    'Action Required': 's-action',
    'Verified': 's-verified',
    'Submitted': 's-submitted',
    'Overdue': 's-overdue'
  };

  const STATUS_BADGE_CLASS = {
    'Uploaded': 'badge-uploaded',
    'Pending Approval': 'badge-pending',
    'Action Required': 'badge-action',
    'Verified': 'badge-verified',
    'Submitted': 'badge-submitted',
    'Overdue': 'badge-overdue',
    'Archived': 'badge-archived'
  };

  const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

  let summaryData = {};
  let currentUser = null;
  let allUsers = [];
  let activeSelection = { category: null, status: null };

  let dashboardInitialized = false;

  async function initDashboard() {
    const main = document.getElementById('dashboard-body') 
      || document.querySelector('main') 
      || document.querySelector('.main-content');
    if (main && originalMainHTML) {
      main.innerHTML = originalMainHTML;
    }

    if (dashboardInitialized) {
      await Promise.all([loadSummary(), loadUsers()]);
      renderCategoryCards();
      return;
    }
    dashboardInitialized = true;
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, PAGE_URL);
    await Promise.all([loadSummary(), loadUsers()]);
    renderCategoryCards();
    initUploadModal();
  }

  window.initDashboard = initDashboard;

  let originalMainHTML = null;

  function showLoginPrompt() {
    const main = document.getElementById('dashboard-body') 
      || document.querySelector('main') 
      || document.querySelector('.main-content');
    
    if (!main) return;

    if (!originalMainHTML) {
      originalMainHTML = main.innerHTML;
    }

    main.innerHTML = `
      <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 60vh;
        gap: 12px;
        text-align: center;
      ">
        <div style="font-size: 48px;">🔒</div>
        <h2 style="color: var(--text-primary); font-size: 20px; font-weight: 600; margin: 0;">
          Sign in to continue
        </h2>
        <p style="color: var(--text-secondary); font-size: 14px; margin: 0;">
          Click the account button in the top right to sign in.
        </p>
      </div>
    `;
  }

  // ── Init ─────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', async () => {
    // Init topbar first — this renders the topbar HTML into the DOM
    await window.AE.initTopbar({ showBack: true, backHref: '/index.html' });
    window.AE.initSidebar(PAGE_KEY);

    window.onAuthChange = handleAuthChange;

    // NOW check session — after topbar is done, not before
    const token = localStorage.getItem('ae_token');
    let user = null;
    try {
      const stored = localStorage.getItem('ae_user');
      if (stored) user = JSON.parse(stored);
    } catch(e) {
      localStorage.removeItem('ae_user');
    }

    if (token && user) {
      // Already logged in — update topbar UI and load dashboard
      if (typeof window.updateAccountUI === 'function') {
        window.updateAccountUI(user);
      }
      initDashboard();
    } else {
      // Not logged in — show prompt
      showLoginPrompt();
    }
  });

  async function handleAuthChange(user) {
    currentUser = user;
    if (user) {
      window.AE.initSidebar(PAGE_KEY);
      await initDashboard();
    } else {
      showLoginPrompt();
    }
  }

  // ── Load data ─────────────────────────────────────────────────────────
  async function loadSummary() {
    try {
      const res = await window.AE.apiFetch('/api/documents/summary');
      if (res.ok) summaryData = await res.json();
    } catch (e) { console.error('Failed to load summary', e); }
  }

  async function loadUsers() {
    try {
      const res = await window.AE.apiFetch('/api/users');
      if (res.ok) allUsers = await res.json();
    } catch (e) { /* silent */ }
  }

  // ── Category Cards ────────────────────────────────────────────────────
  function renderCategoryCards() {
    const container = document.getElementById('dashboard-top');
    if (!container) return;

    const cats = Object.keys(CATEGORIES);
    container.innerHTML = cats.map(cat => {
      const catData = summaryData[cat] || {};
      const total = STATUSES.reduce((sum, s) => sum + (catData[s] || 0), 0);
      return `
        <div class="category-card" id="cat-card-${slugify(cat)}">
          <div class="category-card-header">
            <span class="category-link" data-cat="${escHtml(cat)}">${escHtml(cat)}</span>
            <span class="category-total mono">${total} docs</span>
          </div>
          ${STATUSES.map(status => {
            const count = catData[status] || 0;
            const pct = total > 0 ? Math.round((count / total) * 100) : 0;
            return `
              <div class="status-slider-row" data-cat="${escHtml(cat)}" data-status="${escHtml(status)}"
                   role="button" tabindex="0" aria-label="${escHtml(status)}: ${count} of ${total}">
                <span class="status-name">${escHtml(status)}</span>
                <div class="status-bar-wrap">
                  <div class="status-bar-fill ${STATUS_CLASS[status] || ''}" data-target="${pct}" style="width:0%"></div>
                </div>
                <span class="status-count">${count} / ${total}</span>
              </div>
            `;
          }).join('')}
        </div>
      `;
    }).join('');

    // Animate bars after render
    requestAnimationFrame(() => {
      document.querySelectorAll('.status-bar-fill').forEach(bar => {
        bar.style.width = bar.dataset.target + '%';
      });
    });

    // Wire status row clicks
    document.querySelectorAll('.status-slider-row').forEach(row => {
      const activate = () => {
        const cat = row.dataset.cat;
        const status = row.dataset.status;

        // Toggle active state
        document.querySelectorAll('.status-slider-row').forEach(r => r.classList.remove('active'));
        row.classList.add('active');

        activeSelection = { category: cat, status };
        loadDocumentPanel(cat, status);
      };
      row.addEventListener('click', activate);
      row.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') activate(); });
    });
  }

  // ── Document Panel ────────────────────────────────────────────────────
  async function loadDocumentPanel(category, status) {
    const panelHeader = document.getElementById('doc-panel-header');
    const panelBody = document.getElementById('doc-panel-body');
    if (!panelHeader || !panelBody) return;

    panelHeader.innerHTML = `
      <div class="doc-panel-title">
        <span class="badge ${STATUS_BADGE_CLASS[status] || ''}">${escHtml(status)}</span>
        ${escHtml(category)}
      </div>
      <span class="mono" style="font-size:11px;color:var(--text-muted);" id="panel-count"></span>
    `;
    panelBody.innerHTML = `<div style="padding:24px;text-align:center;"><span class="spinner"></span></div>`;

    try {
      const params = new URLSearchParams({ category, status, archived: 'false', latest: 'true' });
      const res = await window.AE.apiFetch(`/api/documents?${params}`);
      const docs = await res.json();

      const countEl = document.getElementById('panel-count');
      if (countEl) countEl.textContent = `${docs.length} document${docs.length !== 1 ? 's' : ''}`;

      if (docs.length === 0) {
        panelBody.innerHTML = `<div class="doc-panel-empty">No documents found for this status.</div>`;
        return;
      }

      panelBody.innerHTML = `
        <table class="doc-table">
          <thead>
            <tr>
              <th>Document Name</th>
              <th>Subcategory</th>
              <th>Last Updated By</th>
              <th>Version</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            ${docs.map(doc => renderDocRow(doc)).join('')}
          </tbody>
        </table>
      `;

      // Wire row clicks
      panelBody.querySelectorAll('tr[data-doc-id]').forEach(row => {
        row.addEventListener('click', e => {
          if (e.target.closest('.doc-actions')) return;
          openFileDetail(parseInt(row.dataset.docId));
        });
      });

      // Wire action buttons
      panelBody.querySelectorAll('.btn-approve').forEach(btn => {
        btn.addEventListener('click', e => { e.stopPropagation(); approveDocument(parseInt(btn.dataset.id)); });
      });
      panelBody.querySelectorAll('.btn-edit').forEach(btn => {
        btn.addEventListener('click', e => { e.stopPropagation(); openEditModal(parseInt(btn.dataset.id)); });
      });
      panelBody.querySelectorAll('.btn-dl').forEach(btn => {
        btn.addEventListener('click', e => { e.stopPropagation(); downloadDocument(parseInt(btn.dataset.id), btn.dataset.name); });
      });

    } catch (err) {
      panelBody.innerHTML = `<div class="doc-panel-empty">Failed to load documents.</div>`;
    }
  }

  function renderDocRow(doc) {
    const canApprove = doc.status === 'Pending Approval' && currentUser && doc.approver_id === currentUser.id;
    return `
      <tr data-doc-id="${doc.id}" style="cursor:pointer;">
        <td><span class="doc-filename">${escHtml(doc.name)}</span></td>
        <td><span class="badge badge-uploaded" style="font-size:10px;">${escHtml(doc.subcategory)}</span></td>
        <td style="color:var(--text-secondary);font-size:12px;">${escHtml(doc.last_uploader_name || '—')}</td>
        <td><span class="mono" style="font-size:12px;color:var(--text-muted);">v${doc.version}</span></td>
        <td>
          <div class="doc-actions">
            ${canApprove ? `<button class="btn btn-sm btn-primary btn-approve" data-id="${doc.id}">Approve</button>` : ''}
            <button class="btn-icon btn-edit" data-id="${doc.id}" title="Edit / Upload new version">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            </button>
            <button class="btn-icon btn-dl" data-id="${doc.id}" data-name="${escHtml(doc.original_filename)}" title="Download">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  // ── File Detail Panel ─────────────────────────────────────────────────
  async function openFileDetail(docId) {
    try {
      const [docRes, versRes] = await Promise.all([
        window.AE.apiFetch(`/api/documents/${docId}`),
        window.AE.apiFetch(`/api/documents/${docId}/versions`)
      ]);
      const doc = await docRes.json();
      const versions = await versRes.json();

      const overlay = document.createElement('div');
      overlay.className = 'file-detail-overlay';
      overlay.id = 'file-detail-overlay';

      const dueDate = doc.due_date ? new Date(doc.due_date) : null;
      const isOverdue = dueDate && dueDate < new Date() && doc.status !== 'Verified' && doc.status !== 'Submitted';
      const canApprove = doc.status === 'Pending Approval' && currentUser && doc.approver_id === currentUser.id;

      overlay.innerHTML = `
        <div class="file-detail-panel" role="dialog" aria-label="File details">
          <div class="file-detail-header">
            <h2 class="file-detail-title">${escHtml(doc.name)}</h2>
            <button class="file-detail-close" id="detail-close" aria-label="Close">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="file-detail-meta">
            <span class="badge ${STATUS_BADGE_CLASS[doc.status] || ''}" id="file-detail-status-badge">${escHtml(doc.status)}</span>
            <span class="badge" style="background:var(--bg-raised);color:var(--text-secondary);">${escHtml(doc.category)}</span>
            <span class="badge" style="background:var(--bg-raised);color:var(--text-secondary);">${escHtml(doc.subcategory)}</span>
            <span class="mono badge" style="background:var(--bg-raised);color:var(--text-muted);font-size:11px;">v${doc.version}</span>
          </div>
          <div class="file-detail-actions">
            ${canApprove ? `<button class="btn btn-primary btn-sm" id="detail-approve">✓ Approve</button>` : ''}
            <button class="btn btn-ghost btn-sm" id="detail-edit">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              Edit
            </button>
            <button class="btn btn-ghost btn-sm" id="detail-download">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Download
            </button>
            <button class="btn btn-ghost btn-sm" id="detail-archive" style="color:var(--status-overdue);">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
              Archive
            </button>
          </div>
          <div class="file-detail-info">
            ${infoRow('Original Uploader', escHtml(doc.original_uploader_name || '—'))}
            ${infoRow('Last Updated By', escHtml(doc.last_uploader_name || '—'))}
            ${infoRow('Uploaded On', formatDate(doc.upload_date))}
            ${infoRow('Due Date', dueDate
              ? `<span class="${isOverdue ? 'overdue' : ''}">${formatDate(doc.due_date)}${isOverdue ? ' ⚠ Overdue' : ''}</span>`
              : '—')}
            ${infoRow('Approver', escHtml(doc.approver_name || 'None'))}
            ${infoRow('Month / Year', `${escHtml(doc.month)} ${escHtml(doc.year)}`)}
            ${infoRow('Editable', doc.is_editable
              ? `<span class="badge badge-verified">Yes</span>`
              : `<span class="badge badge-action">Locked</span>`)}
          </div>
          <div class="divider" style="margin:0 20px;"></div>
          <div class="file-detail-versions">
            <h3>Version History</h3>
            ${versions.map(v => `
              <div class="version-item">
                <div class="version-item-info">
                  <div class="version-num">v${v.version}</div>
                  <div class="version-meta">${formatDate(v.upload_date)} · ${escHtml(v.last_uploader_name || '—')}</div>
                </div>
                <button class="btn-icon" onclick="window.AE.downloadDoc(${v.id}, '${escAttr(v.original_filename)}')" title="Download v${v.version}">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </button>
              </div>
            `).join('')}
          </div>
        </div>
      `;

      document.body.appendChild(overlay);

      // Wire buttons
      document.getElementById('detail-close').addEventListener('click', closeFileDetail);
      overlay.addEventListener('click', e => { if (e.target === overlay) closeFileDetail(); });
      document.addEventListener('keydown', handleDetailEsc);

      if (document.getElementById('detail-approve')) {
        document.getElementById('detail-approve').addEventListener('click', async () => {
          await approveDocument(doc.id);
          closeFileDetail();
          await loadSummary();
          renderCategoryCards();
          if (activeSelection.category) loadDocumentPanel(activeSelection.category, activeSelection.status);
        });
      }

      document.getElementById('detail-edit').addEventListener('click', () => {
        closeFileDetail();
        openEditModal(doc.id);
      });

      document.getElementById('detail-download').addEventListener('click', () => {
        downloadDocument(doc.id, doc.original_filename);
      });

      document.getElementById('detail-archive').addEventListener('click', async () => {
        await archiveDocument(doc.id);
        closeFileDetail();
        await loadSummary();
        renderCategoryCards();
        if (activeSelection.category) loadDocumentPanel(activeSelection.category, activeSelection.status);
      });

    } catch (err) {
      console.error('Failed to open file detail', err);
    }
  }

  function infoRow(label, valueHtml) {
    return `
      <div class="file-detail-row">
        <span class="file-detail-row-label">${label}</span>
        <span class="file-detail-row-value">${valueHtml}</span>
      </div>
    `;
  }

  function handleDetailEsc(e) {
    if (e.key === 'Escape') closeFileDetail();
  }

  function closeFileDetail() {
    const overlay = document.getElementById('file-detail-overlay');
    if (overlay) overlay.remove();
    document.removeEventListener('keydown', handleDetailEsc);
  }

  // ── Actions ───────────────────────────────────────────────────────────
  async function approveDocument(id) {
    try {
      await window.AE.apiFetch(`/api/documents/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status: 'Verified' })
      });
    } catch (e) { console.error('Approve failed', e); }
  }

  async function archiveDocument(id) {
    try {
      await window.AE.apiFetch(`/api/documents/${id}/archive`, { method: 'PATCH' });
    } catch (e) { console.error('Archive failed', e); }
  }

  async function downloadDocument(id, filename) {
    try {
      const token = window.AE.getToken();
      const a = document.createElement('a');
      a.href = `/api/documents/${id}/download`;
      a.download = filename || 'document';
      // Use fetch with auth to get blob
      const res = await window.AE.apiFetch(`/api/documents/${id}/download`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      a.href = url;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { console.error('Download failed', e); }
  }

  window.AE.downloadDoc = downloadDocument;

  // ── Upload Modal ──────────────────────────────────────────────────────
  function initUploadModal() {
    const btn = document.getElementById('upload-btn');
    if (btn) btn.addEventListener('click', () => openUploadModal(null));
  }

  function openUploadModal(editDocId, doc = null) {
    const isEdit = !!editDocId;
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'upload-modal-overlay';

    const currentYear = new Date().getFullYear();
    const years = [];
    for (let y = currentYear - 4; y <= currentYear + 2; y++) years.push(y);

    overlay.innerHTML = `
      <div class="modal" role="dialog" aria-label="${isEdit ? 'Upload new version' : 'Upload document'}">
        <div class="modal-header">
          <h2>${isEdit ? 'Upload New Version' : 'Upload Document'}</h2>
          <button class="file-detail-close" id="modal-close" aria-label="Close">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body">
          ${isEdit ? `
          <!-- Status-only update section -->
          <div id="edit-status-section" style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid var(--border);">
            <label style="display:block; font-size:13px; color:var(--text-secondary); margin-bottom:6px;">
              Change Status
            </label>
            <select id="edit-status-select" style="width:100%; padding:8px 10px; border-radius:4px; border:1px solid var(--border); background:var(--bg-surface); color:var(--text-primary); font-size:14px;">
              <option value="Uploaded">Uploaded</option>
              <option value="Pending Approval">Pending Approval</option>
              <option value="Action Required">Action Required</option>
              <option value="Verified">Verified</option>
              <option value="Submitted">Submitted</option>
              <option value="Overdue">Overdue</option>
            </select>
            <button type="button" id="edit-status-save-btn"
              style="margin-top:10px; padding:8px 16px; background:var(--accent); color:#fff; border:none; border-radius:4px; font-size:14px; cursor:pointer;">
              Update Status
            </button>
            <span id="edit-status-feedback" style="display:none; margin-left:10px; font-size:13px;"></span>
          </div>
          ` : ''}

          ${!isEdit ? `
          <div class="modal-grid-2">
            <div class="form-group">
              <label for="up-month">Month *</label>
              <select id="up-month">
                <option value="">Select month</option>
                ${MONTHS.map((m, i) => `<option value="${m}">${m}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="up-year">Year *</label>
              <select id="up-year">
                <option value="">Select year</option>
                ${years.map(y => `<option value="${y}" ${y === currentYear ? 'selected' : ''}>${y}</option>`).join('')}
              </select>
            </div>
          </div>
          <div class="form-group">
            <label for="up-name">Document Name *</label>
            <input type="text" id="up-name" placeholder="e.g. Q1 GST Return 2024" />
          </div>
          <div class="modal-grid-2">
            <div class="form-group">
              <label for="up-category">Category *</label>
              <select id="up-category">
                <option value="">Select category</option>
                ${Object.keys(CATEGORIES).map(c => `<option value="${c}">${c}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="up-subcategory">Subcategory *</label>
              <select id="up-subcategory" disabled>
                <option value="">Select category first</option>
              </select>
            </div>
          </div>
          ` : ''}

          ${isEdit ? `
          <div id="edit-file-section" style="margin-top: 10px;">
            <label style="display:block; font-size:13px; color:var(--text-secondary); margin-bottom:6px;">
              Upload New Version (optional)
            </label>
          </div>
          ` : ''}

          <div class="modal-grid-2">
            <div class="form-group">
              <label for="up-status">Status *</label>
              <select id="up-status">
                ${STATUSES.map(s => `<option value="${s}">${s}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label for="up-due-date">Due Date</label>
              <input type="date" id="up-due-date" />
            </div>
          </div>
          <div class="form-group">
            <label for="up-approver">Approver</label>
            <select id="up-approver">
              <option value="">None</option>
              ${allUsers.map(u => `<option value="${u.id}">${escHtml(u.name)}</option>`).join('')}
            </select>
          </div>
          <div class="form-group">
            <label>Editable</label>
            <div class="toggle-wrap">
              <button class="toggle on" id="up-editable-toggle" type="button" aria-pressed="true" aria-label="Toggle editable"></button>
              <span class="toggle-label" id="up-editable-label">Yes — users can upload new versions</span>
            </div>
          </div>
          <div class="form-group">
            <label>File *</label>
            <div class="file-upload-zone" id="up-zone">
              <input type="file" id="up-file" accept="*/*" />
              <div class="file-upload-zone-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              </div>
              <p>Click to browse or drag & drop</p>
              <p class="file-name" id="up-file-name"></p>
            </div>
          </div>
          <p class="login-error" id="upload-error"></p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" id="modal-cancel">Cancel</button>
          <button class="btn btn-primary" id="modal-submit">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            ${isEdit ? 'Upload Version' : 'Upload Document'}
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // Close
    const close = () => { overlay.remove(); document.removeEventListener('keydown', escHandler); };
    const escHandler = e => { if (e.key === 'Escape') close(); };
    document.getElementById('modal-close').addEventListener('click', close);
    document.getElementById('modal-cancel').addEventListener('click', close);
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    document.addEventListener('keydown', escHandler);

    // Category → subcategory
    if (!isEdit) {
      document.getElementById('up-category').addEventListener('change', function () {
        const subSel = document.getElementById('up-subcategory');
        const subs = CATEGORIES[this.value] || [];
        subSel.disabled = subs.length === 0;
        subSel.innerHTML = subs.length
          ? `<option value="">Select subcategory</option>${subs.map(s => `<option value="${s}">${s}</option>`).join('')}`
          : `<option value="">Select category first</option>`;
      });
    }

    // Toggle
    const toggleBtn = document.getElementById('up-editable-toggle');
    const toggleLabel = document.getElementById('up-editable-label');
    let isEditable = true;
    toggleBtn.addEventListener('click', () => {
      isEditable = !isEditable;
      toggleBtn.classList.toggle('on', isEditable);
      toggleBtn.setAttribute('aria-pressed', isEditable);
      toggleLabel.textContent = isEditable ? 'Yes — users can upload new versions' : 'No — document is locked';
    });

    // File input
    document.getElementById('up-file').addEventListener('change', function () {
      const nameEl = document.getElementById('up-file-name');
      nameEl.textContent = this.files[0] ? this.files[0].name : '';
    });

    // Drag & drop
    const zone = document.getElementById('up-zone');
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('dragover');
      const fileInput = document.getElementById('up-file');
      if (e.dataTransfer.files.length) {
        const dt = new DataTransfer();
        dt.items.add(e.dataTransfer.files[0]);
        fileInput.files = dt.files;
        document.getElementById('up-file-name').textContent = e.dataTransfer.files[0].name;
      }
    });

    // Populate and disable if Edit mode
    if (isEdit && doc) {
      const statusSelect = document.getElementById('edit-status-select');
      const upStatusSelect = document.getElementById('up-status');
      const upDueDate = document.getElementById('up-due-date');
      const upApprover = document.getElementById('up-approver');
      const saveBtn = document.getElementById('edit-status-save-btn');

      if (statusSelect) {
        statusSelect.value = doc.status;
        if (doc.is_archived) {
          statusSelect.disabled = true;
          if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.title = 'Unarchive this document to change its status.';
          }
        }
      }

      if (upStatusSelect) upStatusSelect.value = doc.status;
      if (upDueDate && doc.due_date) upDueDate.value = doc.due_date.split('T')[0];
      if (upApprover && doc.approver_id) upApprover.value = doc.approver_id;

      if (toggleBtn && toggleLabel) {
        isEditable = doc.is_editable === 1 || doc.is_editable === true;
        toggleBtn.classList.toggle('on', isEditable);
        toggleBtn.setAttribute('aria-pressed', isEditable);
        toggleLabel.textContent = isEditable ? 'Yes — users can upload new versions' : 'No — document is locked';
      }

      if (saveBtn) {
        saveBtn.dataset.docId = editDocId;
      }
    }

    // Wire status-only update button
    const editStatusSaveBtn = document.getElementById('edit-status-save-btn');
    if (editStatusSaveBtn) {
      editStatusSaveBtn.addEventListener('click', async function () {
        const docId = this.dataset.docId;
        const newStatus = document.getElementById('edit-status-select').value;
        const feedbackEl = document.getElementById('edit-status-feedback');

        this.disabled = true;
        this.textContent = 'Saving…';
        feedbackEl.style.display = 'none';

        try {
          const res = await window.AE.apiFetch(`/api/documents/${docId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status: newStatus })
          });

          const data = await res.json();

          if (!res.ok) {
            feedbackEl.textContent = data.error || 'Failed to update status.';
            feedbackEl.style.color = 'var(--status-action)';
            feedbackEl.style.display = 'inline';
            return;
          }

          feedbackEl.textContent = '✓ Status updated';
          feedbackEl.style.color = 'var(--status-verified)';
          feedbackEl.style.display = 'inline';

          // Update file detail badge if present
          const detailStatusBadge = document.getElementById('file-detail-status-badge');
          if (detailStatusBadge) {
            detailStatusBadge.textContent = newStatus;
            detailStatusBadge.className = `badge ${STATUS_BADGE_CLASS[newStatus] || ''}`;
          }

          // Refresh the view
          await loadSummary();
          renderCategoryCards();
          if (activeSelection.category) {
            loadDocumentPanel(activeSelection.category, activeSelection.status);
          }

          setTimeout(() => {
            close();
          }, 800);

        } catch (err) {
          feedbackEl.textContent = 'Could not reach server.';
          feedbackEl.style.color = 'var(--status-action)';
          feedbackEl.style.display = 'inline';
          console.error('[STATUS UPDATE ERROR]', err);
        } finally {
          this.disabled = false;
          this.textContent = 'Update Status';
        }
      });
    }

    // Submit
    document.getElementById('modal-submit').addEventListener('click', async () => {
      await handleUpload(isEdit ? editDocId : null, isEditable, close);
    });
  }

  async function openEditModal(docId) {
    try {
      const res = await window.AE.apiFetch(`/api/documents/${docId}`);
      if (!res.ok) return;
      const doc = await res.json();
      openUploadModal(docId, doc);
    } catch (e) {
      console.error('Failed to open edit modal', e);
    }
  }

  async function handleUpload(editDocId, isEditable, closeFn) {
    const errEl = document.getElementById('upload-error');
    const submitBtn = document.getElementById('modal-submit');
    const fileInput = document.getElementById('up-file');
    const isEdit = !!editDocId;

    errEl.textContent = '';

    if (!fileInput.files[0]) { errEl.textContent = 'Please select a file.'; return; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('is_editable', isEditable ? '1' : '0');

    const status = document.getElementById('up-status').value;
    const dueDate = document.getElementById('up-due-date').value;
    const approverId = document.getElementById('up-approver').value;

    formData.append('status', status);
    if (dueDate) formData.append('due_date', dueDate);
    if (approverId) formData.append('approver_id', approverId);

    if (!isEdit) {
      const name = document.getElementById('up-name').value.trim();
      const category = document.getElementById('up-category').value;
      const subcategory = document.getElementById('up-subcategory').value;
      const month = document.getElementById('up-month').value;
      const year = document.getElementById('up-year').value;
      if (!name || !category || !subcategory || !month || !year) {
        errEl.textContent = 'Please fill in all required fields.'; return;
      }
      formData.append('name', name);
      formData.append('category', category);
      formData.append('subcategory', subcategory);
      formData.append('month', month);
      formData.append('year', year);
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Uploading…';

    try {
      const url = isEdit ? `/api/documents/${editDocId}/edit` : '/api/documents/upload';
      const res = await window.AE.apiFetch(url, { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        closeFn();
        await loadSummary();
        renderCategoryCards();
        if (activeSelection.category) loadDocumentPanel(activeSelection.category, activeSelection.status);
      } else {
        console.error('[UPLOAD FAILED]', data);
        errEl.textContent = data.detail || data.error || 'Upload failed.';
        submitBtn.disabled = false;
        submitBtn.textContent = isEdit ? 'Upload Version' : 'Upload Document';
      }
    } catch (e) {
      errEl.textContent = 'Network error. Please try again.';
      submitBtn.disabled = false;
      submitBtn.textContent = isEdit ? 'Upload Version' : 'Upload Document';
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────
  function escHtml(str) {
    if (!str && str !== 0) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function escAttr(str) {
    return escHtml(str).replace(/'/g, '&#39;');
  }

  function formatDate(str) {
    if (!str) return '—';
    const d = new Date(str);
    return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  function slugify(str) {
    return str.toLowerCase().replace(/\s+/g, '-');
  }
})();
