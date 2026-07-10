/* =====================================================================
   vault.js — Document Vault page logic
   Search, filters, document table, multi-select, bulk actions
   ===================================================================== */

(function () {
  const PAGE_KEY = 'doc-vault';
  const PAGE_LABEL = 'Document Vault';
  const PAGE_URL = '/documents/vault.html';
  const IS_ARCHIVES = window.location.pathname.includes('archives');

  const CATEGORIES = {
    'Indirect Tax': ['GST Returns', 'VAT Filings', 'Customs Duty', 'Service Tax', 'Excise'],
    'Employees': ['Payroll', 'PF/ESI', 'TDS on Salary', 'Leave Records', 'Contracts'],
    'Income Tax': ['ITR Filing', 'Advance Tax', 'TDS Returns', 'Form 16', 'Tax Audit Report'],
    'Asset Management': ['Fixed Assets Register', 'Depreciation Schedules', 'Asset Purchase Invoices', 'Asset Disposal Records', 'Insurance Policies', 'Lease Agreements', 'Asset Valuation Reports'],
    'Sales Management': ['Sales Invoices', 'Customer Contracts', 'Sales Returns', 'Debtors Ledger', 'Sales Tax Returns', 'Credit Notes', 'Sales Reports']
  };

  const STATUSES = ['Uploaded', 'Pending Approval', 'Action Required', 'Verified', 'Submitted', 'Overdue'];

  const STATUS_BADGE = {
    'Uploaded': 'badge-uploaded',
    'Pending Approval': 'badge-pending',
    'Action Required': 'badge-action',
    'Verified': 'badge-verified',
    'Submitted': 'badge-submitted',
    'Overdue': 'badge-overdue',
    'Archived': 'badge-archived'
  };

  const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

  let currentUser = null;
  let allUsers = [];
  let allDocs = [];
  let selectedIds = new Set();
  let lastCheckedIndex = -1;

  // Filters state
  let filters = {
    search: '',
    statuses: new Set(),
    category: '',
    subcategory: '',
    month: '',
    year: '',
    uploader_id: ''
  };

  let searchDebounce = null;

  let vaultInitialized = false;

  async function initVault() {
    const main = document.getElementById('vault-body')
      || document.getElementById('archives-body')
      || document.querySelector('main')
      || document.querySelector('.main-content');
    if (main && originalMainHTML) {
      main.innerHTML = originalMainHTML;
    }

    if (vaultInitialized) {
      await fetchDocs();
      renderTable();
      return;
    }
    vaultInitialized = true;
    const pageKey = IS_ARCHIVES ? 'doc-archives' : PAGE_KEY;
    const pageLabel = IS_ARCHIVES ? 'Archives' : PAGE_LABEL;
    const pageUrl = IS_ARCHIVES ? '/documents/archives.html' : PAGE_URL;

    window.AE.trackVisit(pageKey, pageLabel, pageUrl);
    await loadUsers();
    renderFilters();
    await fetchDocs();
    renderTable();
  }

  window.initVault = initVault;
  window.initArchives = initVault;

  let originalMainHTML = null;

  function showLoginPrompt() {
    const main = document.getElementById('vault-body')
      || document.getElementById('archives-body')
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
    const pageKey = IS_ARCHIVES ? 'doc-archives' : PAGE_KEY;

    // Init topbar first — this renders the topbar HTML into the DOM
    await window.AE.initTopbar({ showBack: true, backHref: '/index.html' });
    window.AE.initSidebar(pageKey);

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
      // Already logged in — update topbar UI and load vault/archives
      if (typeof window.updateAccountUI === 'function') {
        window.updateAccountUI(user);
      }
      initVault();
    } else {
      // Not logged in — show prompt
      showLoginPrompt();
    }
  });

  async function handleAuthChange(user) {
    currentUser = user;
    if (user) {
      const pageKey = IS_ARCHIVES ? 'doc-archives' : PAGE_KEY;
      window.AE.initSidebar(pageKey);
      await initVault();
    } else {
      showLoginPrompt();
    }
  }

  // ── Load data ─────────────────────────────────────────────────────────
  async function loadUsers() {
    try {
      const res = await window.AE.apiFetch('/api/users');
      if (res.ok) allUsers = await res.json();
    } catch (e) { /* silent */ }
  }

  async function fetchDocs() {
    const params = new URLSearchParams({ latest: 'true', archived: IS_ARCHIVES ? 'true' : 'false' });
    if (filters.search) params.append('search', filters.search);
    if (filters.category) params.append('category', filters.category);
    if (filters.subcategory) params.append('subcategory', filters.subcategory);
    if (filters.month) params.append('month', filters.month);
    if (filters.year) params.append('year', filters.year);
    if (filters.uploader_id) params.append('uploader_id', filters.uploader_id);
    if (filters.statuses.size === 1) params.append('status', [...filters.statuses][0]);

    try {
      const res = await window.AE.apiFetch(`/api/documents?${params}`);
      if (res.ok) {
        let docs = await res.json();
        // Client-side multi-status filter (API only handles single status)
        if (filters.statuses.size > 1) {
          docs = docs.filter(d => filters.statuses.has(d.status));
        }
        allDocs = docs;
      }
    } catch (e) { console.error('Fetch docs failed', e); allDocs = []; }
  }

  // ── Render Filters Panel ──────────────────────────────────────────────
  function renderFilters() {
    const panel = document.getElementById('vault-filters-content');
    if (!panel) return;

    const currentYear = new Date().getFullYear();
    const years = [];
    for (let y = currentYear - 4; y <= currentYear + 2; y++) years.push(y);

    panel.innerHTML = `
      <!-- Search -->
      <div class="search-input-wrap">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" id="vault-search" placeholder="Search by name…" value="${escHtml(filters.search)}" />
      </div>

      <!-- Active filter chips -->
      <div id="active-filters-wrap" style="display:none;">
        <div class="filter-group-label">Active Filters</div>
        <div class="active-filters" id="active-filters"></div>
        <button class="clear-all-btn" id="clear-all-btn">Clear all</button>
      </div>

      <div>
        <div class="filter-group-label">Status</div>
        <div class="chip-group">
          ${STATUSES.map(s => `
            <button class="chip ${filters.statuses.has(s) ? 'active' : ''}" data-status="${escHtml(s)}">${escHtml(s)}</button>
          `).join('')}
        </div>
      </div>

      <div class="form-group">
        <div class="filter-group-label">Category</div>
        <select id="filter-category">
          <option value="">All Categories</option>
          ${Object.keys(CATEGORIES).map(c => `<option value="${c}" ${filters.category===c?'selected':''}>${c}</option>`).join('')}
        </select>
      </div>

      <div class="form-group">
        <div class="filter-group-label">Subcategory</div>
        <select id="filter-subcategory" ${!filters.category ? 'disabled' : ''}>
          <option value="">All Subcategories</option>
          ${(CATEGORIES[filters.category] || []).map(s => `<option value="${s}" ${filters.subcategory===s?'selected':''}>${s}</option>`).join('')}
        </select>
      </div>

      <div class="modal-grid-2">
        <div class="form-group">
          <div class="filter-group-label">Month</div>
          <select id="filter-month">
            <option value="">All</option>
            ${MONTHS.map(m => `<option value="${m}" ${filters.month===m?'selected':''}>${m}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <div class="filter-group-label">Year</div>
          <select id="filter-year">
            <option value="">All</option>
            ${years.map(y => `<option value="${y}" ${filters.year==y?'selected':''}>${y}</option>`).join('')}
          </select>
        </div>
      </div>

      <div class="form-group">
        <div class="filter-group-label">Uploaded By</div>
        <select id="filter-uploader">
          <option value="">All Users</option>
          ${allUsers.map(u => `<option value="${u.id}" ${filters.uploader_id==u.id?'selected':''}>${escHtml(u.name)}</option>`).join('')}
        </select>
      </div>
    `;

    // Wire events
    const searchInput = document.getElementById('vault-search');
    searchInput.addEventListener('input', () => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(async () => {
        filters.search = searchInput.value.trim();
        updateActiveFilters();
        await fetchDocs();
        renderTable();
      }, 300);
    });

    panel.querySelectorAll('.chip[data-status]').forEach(chip => {
      chip.addEventListener('click', async () => {
        const s = chip.dataset.status;
        if (filters.statuses.has(s)) { filters.statuses.delete(s); chip.classList.remove('active'); }
        else { filters.statuses.add(s); chip.classList.add('active'); }
        updateActiveFilters();
        await fetchDocs();
        renderTable();
      });
    });

    const catSel = document.getElementById('filter-category');
    catSel.addEventListener('change', async () => {
      filters.category = catSel.value;
      filters.subcategory = '';
      const subSel = document.getElementById('filter-subcategory');
      const subs = CATEGORIES[filters.category] || [];
      subSel.disabled = !subs.length;
      subSel.innerHTML = `<option value="">All Subcategories</option>${subs.map(s=>`<option value="${s}">${s}</option>`).join('')}`;
      updateActiveFilters();
      await fetchDocs();
      renderTable();
    });

    document.getElementById('filter-subcategory').addEventListener('change', async function() {
      filters.subcategory = this.value;
      updateActiveFilters();
      await fetchDocs();
      renderTable();
    });

    document.getElementById('filter-month').addEventListener('change', async function() {
      filters.month = this.value;
      updateActiveFilters();
      await fetchDocs();
      renderTable();
    });

    document.getElementById('filter-year').addEventListener('change', async function() {
      filters.year = this.value;
      updateActiveFilters();
      await fetchDocs();
      renderTable();
    });

    document.getElementById('filter-uploader').addEventListener('change', async function() {
      filters.uploader_id = this.value;
      updateActiveFilters();
      await fetchDocs();
      renderTable();
    });

    document.getElementById('clear-all-btn').addEventListener('click', async () => {
      filters = { search: '', statuses: new Set(), category: '', subcategory: '', month: '', year: '', uploader_id: '' };
      renderFilters();
      await fetchDocs();
      renderTable();
    });

    updateActiveFilters();
  }

  function updateActiveFilters() {
    const wrap = document.getElementById('active-filters-wrap');
    const container = document.getElementById('active-filters');
    if (!wrap || !container) return;

    const chips = [];
    if (filters.search) chips.push({ label: `Search: "${filters.search}"`, clear: () => { filters.search = ''; } });
    if (filters.category) chips.push({ label: `Category: ${filters.category}`, clear: () => { filters.category = ''; filters.subcategory = ''; } });
    if (filters.subcategory) chips.push({ label: `Sub: ${filters.subcategory}`, clear: () => { filters.subcategory = ''; } });
    if (filters.month) chips.push({ label: `Month: ${filters.month}`, clear: () => { filters.month = ''; } });
    if (filters.year) chips.push({ label: `Year: ${filters.year}`, clear: () => { filters.year = ''; } });
    if (filters.uploader_id) {
      const u = allUsers.find(x => x.id == filters.uploader_id);
      chips.push({ label: `By: ${u ? u.name : filters.uploader_id}`, clear: () => { filters.uploader_id = ''; } });
    }
    filters.statuses.forEach(s => chips.push({ label: s, clear: () => { filters.statuses.delete(s); } }));

    wrap.style.display = chips.length ? '' : 'none';
    container.innerHTML = chips.map((c, i) => `
      <span class="filter-chip">
        ${escHtml(c.label)}
        <button class="filter-chip-remove" data-idx="${i}" aria-label="Remove filter">×</button>
      </span>
    `).join('');

    container.querySelectorAll('.filter-chip-remove').forEach(btn => {
      btn.addEventListener('click', async () => {
        chips[parseInt(btn.dataset.idx)].clear();
        renderFilters();
        await fetchDocs();
        renderTable();
      });
    });
  }

  // ── Render Table ──────────────────────────────────────────────────────
  function renderTable() {
    const body = document.getElementById('vault-list-body');
    const header = document.getElementById('vault-list-header');
    if (!body) return;

    // Update count
    const countEl = document.getElementById('vault-doc-count');
    if (countEl) countEl.textContent = `${allDocs.length} document${allDocs.length !== 1 ? 's' : ''}`;

    if (allDocs.length === 0) {
      body.innerHTML = `<div class="empty-state"><svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg><p>No documents found</p></div>`;
      return;
    }

    body.innerHTML = `
      <table class="vault-table">
        <thead>
          <tr>
            <th style="width:32px;"><input type="checkbox" id="select-all" title="Select all" /></th>
            <th>Name</th>
            <th>Category</th>
            <th>Status</th>
            <th>Last Changed By</th>
            <th>Ver.</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="vault-tbody">
          ${allDocs.map((doc, idx) => renderVaultRow(doc, idx)).join('')}
        </tbody>
      </table>
    `;

    // Select all
    document.getElementById('select-all').addEventListener('change', function() {
      if (this.checked) {
        selectedIds = new Set(allDocs.map(d => d.id));
      } else {
        selectedIds.clear();
      }
      renderCheckboxStates();
      updateFloatingBar();
    });

    // Row checkboxes + shift-click
    body.querySelectorAll('.row-checkbox').forEach((cb, idx) => {
      cb.addEventListener('change', function(e) {
        if (e.shiftKey && lastCheckedIndex >= 0) {
          const start = Math.min(lastCheckedIndex, idx);
          const end = Math.max(lastCheckedIndex, idx);
          for (let i = start; i <= end; i++) {
            if (this.checked) selectedIds.add(allDocs[i].id);
            else selectedIds.delete(allDocs[i].id);
          }
        } else {
          if (this.checked) selectedIds.add(allDocs[idx].id);
          else selectedIds.delete(allDocs[idx].id);
        }
        lastCheckedIndex = idx;
        renderCheckboxStates();
        updateFloatingBar();
      });
    });

    // Row clicks → file detail
    body.querySelectorAll('tr[data-doc-id]').forEach(row => {
      row.addEventListener('click', e => {
        if (e.target.closest('.doc-actions') || e.target.type === 'checkbox') return;
        openFileDetail(parseInt(row.dataset.docId));
      });
    });

    // Action buttons
    body.querySelectorAll('.btn-approve').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        await approveDocument(parseInt(btn.dataset.id));
        await fetchDocs();
        renderTable();
      });
    });

    body.querySelectorAll('.btn-edit').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        openEditModal(parseInt(btn.dataset.id));
      });
    });

    body.querySelectorAll('.btn-dl').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        downloadDocument(parseInt(btn.dataset.id), btn.dataset.name);
      });
    });

    body.querySelectorAll('.btn-archive').forEach(btn => {
      btn.addEventListener('click', async e => {
        e.stopPropagation();
        await archiveDocument(parseInt(btn.dataset.id));
        await fetchDocs();
        renderTable();
      });
    });

    renderCheckboxStates();
  }

  function renderVaultRow(doc, idx) {
    const canApprove = doc.status === 'Pending Approval' && currentUser && doc.approver_id === currentUser.id;
    const isSelected = selectedIds.has(doc.id);

    return `
      <tr data-doc-id="${doc.id}" class="${isSelected ? 'selected' : ''}">
        <td><input type="checkbox" class="row-checkbox" ${isSelected ? 'checked' : ''} /></td>
        <td><span class="doc-filename">${escHtml(doc.name)}</span><div style="font-size:10px;color:var(--text-muted);margin-top:2px;">${escHtml(doc.original_filename)}</div></td>
        <td>
          <div style="font-size:11px;color:var(--text-secondary);">${escHtml(doc.category)}</div>
          <div style="font-size:10px;color:var(--text-muted);">${escHtml(doc.subcategory)}</div>
        </td>
        <td><span class="badge ${STATUS_BADGE[doc.status] || ''}">${escHtml(doc.status)}</span></td>
        <td style="font-size:12px;color:var(--text-secondary);">${escHtml(doc.last_uploader_name || '—')}</td>
        <td><span class="mono" style="font-size:12px;color:var(--text-muted);">v${doc.version}</span></td>
        <td>
          <div class="doc-actions">
            ${canApprove ? `<button class="btn btn-sm btn-primary btn-approve" data-id="${doc.id}">Approve</button>` : ''}
            ${!IS_ARCHIVES ? `
              <button class="btn-icon btn-edit" data-id="${doc.id}" title="Upload new version">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
            ` : `
              <button class="btn-icon btn-edit" data-id="${doc.id}" title="Unarchive to edit" disabled style="opacity:0.4;cursor:not-allowed;" data-tooltip="Unarchive to edit">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
            `}
            <button class="btn-icon btn-dl" data-id="${doc.id}" data-name="${escHtml(doc.original_filename)}" title="Download">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            </button>
            <button class="btn-icon btn-archive" data-id="${doc.id}" title="${IS_ARCHIVES ? 'Unarchive' : 'Archive'}" style="color:${IS_ARCHIVES ? 'var(--status-verified)' : 'var(--status-overdue)'}">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  function renderCheckboxStates() {
    document.querySelectorAll('.row-checkbox').forEach((cb, idx) => {
      cb.checked = selectedIds.has(allDocs[idx]?.id);
      const row = cb.closest('tr');
      if (row) row.classList.toggle('selected', cb.checked);
    });
    const selectAll = document.getElementById('select-all');
    if (selectAll) {
      selectAll.checked = allDocs.length > 0 && selectedIds.size === allDocs.length;
      selectAll.indeterminate = selectedIds.size > 0 && selectedIds.size < allDocs.length;
    }
  }

  // ── Floating Action Bar ───────────────────────────────────────────────
  function updateFloatingBar() {
    const bar = document.getElementById('floating-bar');
    if (!bar) return;
    if (selectedIds.size > 0) {
      bar.classList.add('visible');
      bar.querySelector('.fab-count').textContent = selectedIds.size;
    } else {
      bar.classList.remove('visible');
    }
  }

  function initFloatingBar() {
    const bar = document.getElementById('floating-bar');
    if (!bar) return;
    bar.querySelector('#fab-archive-btn').addEventListener('click', async () => {
      const ids = [...selectedIds];
      await Promise.all(ids.map(id => archiveDocument(id)));
      selectedIds.clear();
      updateFloatingBar();
      await fetchDocs();
      renderTable();
    });
    bar.querySelector('#fab-download-btn').addEventListener('click', async () => {
      const ids = [...selectedIds];
      for (const id of ids) {
        const doc = allDocs.find(d => d.id === id);
        if (doc) await downloadDocument(id, doc.original_filename);
        await new Promise(r => setTimeout(r, 200));
      }
    });
    bar.querySelector('#fab-clear-btn').addEventListener('click', () => {
      selectedIds.clear();
      renderCheckboxStates();
      updateFloatingBar();
    });
  }

  // ── File Detail ───────────────────────────────────────────────────────
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
        <div class="file-detail-panel" role="dialog">
          <div class="file-detail-header">
            <h2 class="file-detail-title">${escHtml(doc.name)}</h2>
            <button class="file-detail-close" id="detail-close">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="file-detail-meta">
            <span class="badge ${STATUS_BADGE[doc.status] || ''}" id="file-detail-status-badge">${escHtml(doc.status)}</span>
            <span class="badge" style="background:var(--bg-raised);color:var(--text-secondary);">${escHtml(doc.category)}</span>
            <span class="badge" style="background:var(--bg-raised);color:var(--text-secondary);">${escHtml(doc.subcategory)}</span>
            <span class="mono badge" style="background:var(--bg-raised);color:var(--text-muted);font-size:11px;">v${doc.version}</span>
          </div>
          <div class="file-detail-actions">
            ${canApprove ? `<button class="btn btn-primary btn-sm" id="detail-approve">✓ Approve</button>` : ''}
            ${!IS_ARCHIVES ? `
              <button class="btn btn-ghost btn-sm" id="detail-edit">
                <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                Edit
              </button>
            ` : ''}
            <button class="btn btn-ghost btn-sm" id="detail-download">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              Download
            </button>
            <button class="btn btn-ghost btn-sm" id="detail-archive">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>
              ${IS_ARCHIVES ? 'Unarchive' : 'Archive'}
            </button>
          </div>
          <div class="file-detail-info">
            ${row('Original Uploader', escHtml(doc.original_uploader_name || '—'))}
            ${row('Last Updated By', escHtml(doc.last_uploader_name || '—'))}
            ${row('Uploaded On', formatDate(doc.upload_date))}
            ${row('Due Date', dueDate ? `<span class="${isOverdue ? 'overdue' : ''}">${formatDate(doc.due_date)}${isOverdue ? ' ⚠' : ''}</span>` : '—')}
            ${row('Approver', escHtml(doc.approver_name || 'None'))}
            ${row('Month / Year', `${escHtml(doc.month)} ${escHtml(doc.year)}`)}
            ${row('Editable', doc.is_editable ? `<span class="badge badge-verified">Yes</span>` : `<span class="badge badge-action">Locked</span>`)}
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
                <button class="btn-icon" onclick="downloadDocument(${v.id}, '${escHtml(v.original_filename).replace(/'/g,'&#39;')}')" title="Download v${v.version}">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </button>
              </div>
            `).join('')}
          </div>
        </div>
      `;

      document.body.appendChild(overlay);

      const close = () => {
        overlay.remove();
        document.removeEventListener('keydown', escH);
      };
      const escH = e => { if (e.key === 'Escape') close(); };
      document.getElementById('detail-close').addEventListener('click', close);
      overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
      document.addEventListener('keydown', escH);

      if (document.getElementById('detail-approve')) {
        document.getElementById('detail-approve').addEventListener('click', async () => {
          await approveDocument(doc.id);
          close();
          await fetchDocs();
          renderTable();
        });
      }

      if (document.getElementById('detail-edit')) {
        document.getElementById('detail-edit').addEventListener('click', () => {
          close();
          openEditModal(doc.id);
        });
      }

      document.getElementById('detail-download').addEventListener('click', () => {
        downloadDocument(doc.id, doc.original_filename);
      });

      document.getElementById('detail-archive').addEventListener('click', async () => {
        await archiveDocument(doc.id);
        close();
        await fetchDocs();
        renderTable();
      });

    } catch (err) {
      console.error('File detail failed', err);
    }
  }

  function row(label, valueHtml) {
    return `<div class="file-detail-row"><span class="file-detail-row-label">${label}</span><span class="file-detail-row-value">${valueHtml}</span></div>`;
  }

  // ── Edit Modal ────────────────────────────────────────────────────────
  async function openEditModal(docId) {
    if (IS_ARCHIVES) return;
    try {
      const res = await window.AE.apiFetch(`/api/documents/${docId}`);
      if (!res.ok) return;
      const doc = await res.json();
      renderEditModal(docId, doc);
    } catch (e) {
      console.error('Failed to open edit modal', e);
    }
  }

  function renderEditModal(docId, doc) {
    const STATUSES_LOCAL = ['Uploaded', 'Pending Approval', 'Action Required', 'Verified', 'Submitted', 'Overdue'];
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'upload-modal-overlay';

    overlay.innerHTML = `
      <div class="modal" role="dialog" aria-label="Upload new version">
        <div class="modal-header">
          <h2>Upload New Version</h2>
          <button class="file-detail-close" id="modal-close">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body">
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

          <!-- Existing file re-upload section stays below this, unchanged -->
          <div id="edit-file-section" style="margin-top:10px;">
            <label style="display:block; font-size:13px; color:var(--text-secondary); margin-bottom:6px;">
              Upload New Version (optional)
            </label>
          </div>

          <div class="modal-grid-2">
            <div class="form-group">
              <label for="up-status">Status</label>
              <select id="up-status">
                ${STATUSES_LOCAL.map(s => `<option value="${s}">${s}</option>`).join('')}
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
          <button class="btn btn-primary" id="modal-submit">Upload Version</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    const close = () => { overlay.remove(); document.removeEventListener('keydown', escH); };
    const escH = e => { if (e.key === 'Escape') close(); };
    document.getElementById('modal-close').addEventListener('click', close);
    document.getElementById('modal-cancel').addEventListener('click', close);
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    document.addEventListener('keydown', escH);

    // Pre-populate fields
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

    if (saveBtn) {
      saveBtn.dataset.docId = docId;
    }

    // Drag & drop
    const zone = document.getElementById('up-zone');
    if (zone) {
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
    }

    document.getElementById('up-file').addEventListener('change', function() {
      document.getElementById('up-file-name').textContent = this.files[0]?.name || '';
    });

    // Wire status-only update button
    if (saveBtn) {
      saveBtn.addEventListener('click', async function () {
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
            detailStatusBadge.className = `badge ${STATUS_BADGE[newStatus] || ''}`;
          }

          // Refresh the view
          await fetchDocs();
          renderTable();

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

    // Submit new file version
    document.getElementById('modal-submit').addEventListener('click', async () => {
      const errEl = document.getElementById('upload-error');
      const fileInput = document.getElementById('up-file');
      if (!fileInput.files[0]) { errEl.textContent = 'Please select a file.'; return; }

      const formData = new FormData();
      formData.append('file', fileInput.files[0]);
      formData.append('status', document.getElementById('up-status').value);
      const dd = document.getElementById('up-due-date').value;
      if (dd) formData.append('due_date', dd);
      const ap = document.getElementById('up-approver').value;
      if (ap) formData.append('approver_id', ap);

      const btn = document.getElementById('modal-submit');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> Uploading…';

      try {
        const res = await window.AE.apiFetch(`/api/documents/${docId}/edit`, { method: 'POST', body: formData });
        if (res.ok) {
          close();
          await fetchDocs();
          renderTable();
        } else {
          const data = await res.json();
          console.error('[UPLOAD FAILED]', data);
          errEl.textContent = data.detail || data.error || 'Upload failed.';
          btn.disabled = false;
          btn.textContent = 'Upload Version';
        }
      } catch (e) {
        errEl.textContent = 'Network error.';
        btn.disabled = false;
        btn.textContent = 'Upload Version';
      }
    });
  }

  // ── Actions ───────────────────────────────────────────────────────────
  async function approveDocument(id) {
    try {
      await window.AE.apiFetch(`/api/documents/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status: 'Verified' }) });
    } catch (e) { /* silent */ }
  }

  async function archiveDocument(id) {
    try {
      await window.AE.apiFetch(`/api/documents/${id}/archive`, { method: 'PATCH' });
    } catch (e) { /* silent */ }
  }

  async function downloadDocument(id, filename) {
    try {
      const res = await window.AE.apiFetch(`/api/documents/${id}/download`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename || 'document';
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { console.error('Download failed', e); }
  }

  window.downloadDocument = downloadDocument;

  // ── Helpers ───────────────────────────────────────────────────────────
  function escHtml(str) {
    if (!str && str !== 0) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function formatDate(str) {
    if (!str) return '—';
    return new Date(str).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  // Init floating bar
  document.addEventListener('DOMContentLoaded', () => {
    initFloatingBar();
  });
})();
