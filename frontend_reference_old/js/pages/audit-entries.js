/* =====================================================================
   audit-entries.js — Audit Entries list logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Audit Entries';
  const PAGE_URL = '/audit/entries.html';

  let engagementId = null;
  let allEntries = [];

  // Filter state
  let currentTab = 'all'; // 'all', 'pending', 'approved'
  let currentTypeFilter = 'all';
  let searchQuery = '';

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

    // Update subnav links
    const subnav = document.getElementById('audit-subnav');
    if (subnav) {
      subnav.querySelectorAll('a').forEach(link => {
        const page = link.getAttribute('href').split('?')[0];
        link.setAttribute('href', `${page}?id=${engagementId}`);
      });
    }

    // Update New Entry button URL
    const newEntryBtn = document.getElementById('btn-new-entry');
    if (newEntryBtn) {
      newEntryBtn.setAttribute('href', `/audit/entry-form.html?id=${engagementId}`);
    }

    injectSubnavTabs();
    initFilters();
    await loadEntries();
  });

  function injectSubnavTabs() {
    const filterBar = document.getElementById('entries-filter-bar');
    if (!filterBar) return;

    const tabsDiv = document.createElement('div');
    tabsDiv.className = 'tab-buttons';
    tabsDiv.id = 'entries-tabs';
    tabsDiv.style.marginBottom = '16px';
    tabsDiv.innerHTML = `
      <button class="tab-btn active" data-tab="all">All Entries</button>
      <button class="tab-btn" data-tab="pending">Pending Review</button>
      <button class="tab-btn" data-tab="approved">Approved</button>
    `;

    filterBar.parentNode.insertBefore(tabsDiv, filterBar);

    tabsDiv.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        tabsDiv.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTab = btn.dataset.tab;
        renderEntriesTable();
      });
    });
  }

  function initFilters() {
    const search = document.getElementById('search-entries');
    search?.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      renderEntriesTable();
    });

    const chips = document.querySelectorAll('#entry-type-chips .filter-chip');
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        chips.forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        currentTypeFilter = chip.dataset.type;
        renderEntriesTable();
      });
    });
  }

  async function loadEntries() {
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/entries`);
      if (res.ok) {
        allEntries = await res.json();
        renderEntriesTable();
      }
    } catch (e) {
      console.error(e);
      alert('Error loading audit entries.');
    }
  }

  function renderEntriesTable() {
    const container = document.getElementById('entries-table-container');
    if (!container) return;

    let filtered = allEntries;

    // 1. Tab Filter
    if (currentTab === 'pending') {
      filtered = filtered.filter(e => e.status === 'Submitted');
    } else if (currentTab === 'approved') {
      filtered = filtered.filter(e => e.status === 'Approved');
    }

    // 2. Type Filter (Mapping the chips: adjusting, reclassification, elimination)
    if (currentTypeFilter !== 'all') {
      filtered = filtered.filter(e => {
        // Match string case insensitively
        const type = (e.entry_type || '').toLowerCase();
        return type.includes(currentTypeFilter);
      });
    }

    // 3. Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(e =>
        e.entry_number.toLowerCase().includes(q) ||
        e.description.toLowerCase().includes(q) ||
        (e.narration || '').toLowerCase().includes(q)
      );
    }

    if (filtered.length === 0) {
      container.innerHTML = `
        <div class="stat-card" style="text-align: center; padding: 48px;">
          <div style="font-size: 14px; color: var(--text-muted);">No entries match the current filters.</div>
        </div>
      `;
      return;
    }

    const fmt = (v) => v.toLocaleString('en-IN', { minimumFractionDigits: 2 });

    const rowsHtml = filtered.map(e => {
      const statusBadge = `
        <span class="audit-status-badge badge-${e.status.toLowerCase()}">
          ${window.AE.escapeHtml(e.status)}
        </span>
      `;

      let actionsHtml = `<button class="btn btn-secondary btn-sm btn-view-entry" data-id="${e.id}" style="padding:4px 8px;">View</button>`;

      if (e.status === 'Draft' || e.status === 'Rejected') {
        actionsHtml += `
          <a href="/audit/entry-form.html?id=${engagementId}&eid=${e.id}" class="btn btn-secondary btn-sm" style="padding:4px 8px; margin-left:6px; text-decoration:none;">Edit</a>
          <button class="btn btn-primary btn-sm btn-submit-entry" data-id="${e.id}" style="padding:4px 8px; margin-left:6px;">Submit</button>
          <button class="btn btn-ghost btn-sm btn-delete-entry" data-id="${e.id}" style="padding:4px 8px; margin-left:6px; color:var(--status-action);">Delete</button>
        `;
      } else if (e.status === 'Submitted') {
        actionsHtml += `
          <button class="btn btn-primary btn-sm btn-approve-entry" data-id="${e.id}" style="padding:4px 8px; margin-left:6px; background:var(--status-verified); border-color:var(--status-verified);">Approve</button>
          <button class="btn btn-secondary btn-sm btn-reject-entry" data-id="${e.id}" style="padding:4px 8px; margin-left:6px; color:var(--status-action); border-color:var(--status-action);">Reject</button>
        `;
      }

      return `
        <tr>
          <td class="mono"><strong>${window.AE.escapeHtml(e.entry_number)}</strong></td>
          <td>${window.AE.escapeHtml(formatEntryType(e.entry_type))}</td>
          <td>
            <strong>${window.AE.escapeHtml(e.description)}</strong>
            ${e.narration ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${window.AE.escapeHtml(e.narration)}</div>` : ''}
          </td>
          <td class="text-right mono">${fmt(e.total_debit)}</td>
          <td class="text-right mono">${fmt(e.total_credit)}</td>
          <td class="text-center">${e.is_balanced ? '<span style="color:var(--status-verified);font-weight:700;">✓</span>' : '<span style="color:var(--status-action);font-weight:700;">✗</span>'}</td>
          <td>${statusBadge}</td>
          <td style="font-size:12px;color:var(--text-secondary);">${window.AE.escapeHtml(e.created_by_name || 'System')}</td>
          <td style="font-size:12px;color:var(--text-muted);">${e.entry_date}</td>
          <td>
            <div style="display:flex;align-items:center;">
              ${actionsHtml}
            </div>
          </td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <table class="audit-table">
        <thead>
          <tr>
            <th>Entry No.</th>
            <th>Type</th>
            <th>Description</th>
            <th class="text-right">Debit</th>
            <th class="text-right">Credit</th>
            <th class="text-center">Balanced?</th>
            <th>Status</th>
            <th>By</th>
            <th>Date</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    `;

    // Attach row events
    container.querySelectorAll('.btn-view-entry').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = parseInt(btn.dataset.id);
        const entry = allEntries.find(e => e.id === id);
        if (entry) viewEntryDetails(entry);
      });
    });

    container.querySelectorAll('.btn-submit-entry').forEach(btn => {
      btn.addEventListener('click', () => submitEntry(parseInt(btn.dataset.id)));
    });

    container.querySelectorAll('.btn-delete-entry').forEach(btn => {
      btn.addEventListener('click', () => deleteEntry(parseInt(btn.dataset.id)));
    });

    container.querySelectorAll('.btn-approve-entry').forEach(btn => {
      btn.addEventListener('click', () => approveEntry(parseInt(btn.dataset.id)));
    });

    container.querySelectorAll('.btn-reject-entry').forEach(btn => {
      btn.addEventListener('click', () => rejectEntry(parseInt(btn.dataset.id)));
    });
  }

  function formatEntryType(type) {
    if (!type) return '';
    if (type === 'one_to_one') return '1:1 Adjusting';
    if (type === 'one_to_many') return '1:N Adjusting';
    if (type === 'many_to_many') return 'N:N Adjusting';
    return type;
  }

  async function submitEntry(eid) {
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/entries/${eid}/submit`, {
        method: 'POST'
      });
      if (res.ok) {
        await loadEntries();
      } else {
        alert('Failed to submit entry.');
      }
    } catch (e) {
      console.error(e);
      alert('Error submitting entry.');
    }
  }

  async function deleteEntry(eid) {
    if (!confirm('Are you sure you want to delete this entry?')) return;
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/entries/${eid}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        await loadEntries();
      } else {
        alert('Failed to delete entry.');
      }
    } catch (e) {
      console.error(e);
      alert('Error deleting entry.');
    }
  }

  async function approveEntry(eid) {
    if (!confirm('Are you sure you want to APPROVE this entry?')) return;
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/entries/${eid}/approve`, {
        method: 'POST'
      });
      if (res.ok) {
        await loadEntries();
      } else {
        alert('Failed to approve entry.');
      }
    } catch (e) {
      console.error(e);
      alert('Error approving entry.');
    }
  }

  async function rejectEntry(eid) {
    const reason = prompt('Please enter a rejection reason:');
    if (reason === null) return;
    if (!reason.trim()) {
      alert('Rejection reason cannot be empty.');
      return;
    }

    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/entries/${eid}/reject`, {
        method: 'POST',
        body: JSON.stringify({ rejection_reason: reason.trim() })
      });
      if (res.ok) {
        await loadEntries();
      } else {
        alert('Failed to reject entry.');
      }
    } catch (e) {
      console.error(e);
      alert('Error rejecting entry.');
    }
  }

  function viewEntryDetails(entry) {
    let modal = document.getElementById('view-entry-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'view-entry-modal';
      modal.className = 'audit-modal';
      document.body.appendChild(modal);
    }
    modal.style.display = 'flex';

    const fmt = (v) => v.toLocaleString('en-IN', { minimumFractionDigits: 2 });
    const linesHtml = entry.lines.map(l => `
      <tr>
        <td class="mono">${window.AE.escapeHtml(l.ledger_code)}</td>
        <td>${window.AE.escapeHtml(l.ledger_name)}</td>
        <td class="text-right mono">${l.line_type === 'debit' ? fmt(l.amount) : ''}</td>
        <td class="text-right mono">${l.line_type === 'credit' ? fmt(l.amount) : ''}</td>
      </tr>
    `).join('');

    modal.innerHTML = `
      <div class="audit-modal-content" style="max-width: 680px; width: 95%;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
          <h3 style="margin:0;">Entry ${window.AE.escapeHtml(entry.entry_number)}</h3>
          <span class="audit-status-badge badge-${entry.status.toLowerCase()}">${window.AE.escapeHtml(entry.status)}</span>
        </div>
        <div style="margin-bottom:16px; font-size:13px; color:var(--text-secondary); line-height: 1.5; border-bottom: 1px solid var(--border); padding-bottom: 12px;">
          <strong>Description:</strong> ${window.AE.escapeHtml(entry.description)}<br/>
          ${entry.narration ? `<strong>Narration:</strong> ${window.AE.escapeHtml(entry.narration)}<br/>` : ''}
          <strong>Date:</strong> ${entry.entry_date}<br/>
          <strong>Prepared By:</strong> ${window.AE.escapeHtml(entry.created_by_name || 'System')}<br/>
          ${entry.reviewed_by_name ? `<strong>Reviewed By:</strong> ${window.AE.escapeHtml(entry.reviewed_by_name)} &middot; <strong>Date:</strong> ${entry.reviewed_at || ''}<br/>` : ''}
          ${entry.rejection_reason ? `<strong style="color:var(--status-action);">Rejection Reason:</strong> <span style="color:var(--status-action); font-style:italic;">${window.AE.escapeHtml(entry.rejection_reason)}</span><br/>` : ''}
        </div>

        <table class="audit-table">
          <thead>
            <tr>
              <th>Ledger Code</th>
              <th>Ledger Name</th>
              <th class="text-right">Debit</th>
              <th class="text-right">Credit</th>
            </tr>
          </thead>
          <tbody>
            ${linesHtml}
            <tr style="font-weight:700; background:var(--bg-raised);">
              <td colspan="2">TOTAL</td>
              <td class="text-right mono">${fmt(entry.total_debit)}</td>
              <td class="text-right mono">${fmt(entry.total_credit)}</td>
            </tr>
          </tbody>
        </table>

        <div style="display:flex; justify-content:flex-end; gap:12px; margin-top:20px;">
          <button type="button" class="btn btn-secondary" id="btn-close-entry-modal">Close</button>
        </div>
      </div>
    `;

    modal.querySelector('#btn-close-entry-modal').addEventListener('click', () => {
      modal.style.display = 'none';
    });
  }
})();
