/* =====================================================================
   audit-adjusted-tb.js — Adjusted Trial Balance logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Adjusted Trial Balance';
  const PAGE_URL = '/audit/adjusted-tb.html';

  let engagementId = null;
  let ledgers = [];
  let summary = {};

  // Pagination
  let currentPage = 1;
  const limit = 50;

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

    document.getElementById('btn-approve-adj-tb')?.addEventListener('click', approveAdjustedTB);

    await loadAdjustedTB();
  });

  async function loadAdjustedTB() {
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/adjusted-tb`);
      if (res.ok) {
        const data = await res.json();
        ledgers = data.ledgers || [];
        summary = data.summary || {};
        renderStats();
        renderTable();
      }
    } catch (e) {
      console.error(e);
      alert('Error loading Adjusted Trial Balance.');
    }
  }

  function renderStats() {
    const totalAccountsEl = document.getElementById('stat-total-accounts');
    const adjustmentsEl = document.getElementById('stat-adjustments');
    const totalDebitEl = document.getElementById('stat-total-debit');
    const totalCreditEl = document.getElementById('stat-total-credit');
    const balanceCheckEl = document.getElementById('adj-tb-balance-check');

    const adjustedCount = ledgers.filter(l => l.has_adjustment || (l.adj_debit !== 0 || l.adj_credit !== 0)).length;

    if (totalAccountsEl) totalAccountsEl.textContent = ledgers.length;
    if (adjustmentsEl) adjustmentsEl.textContent = adjustedCount;
    if (totalDebitEl) totalDebitEl.textContent = (summary.total_adj_debit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 });
    if (totalCreditEl) totalCreditEl.textContent = (summary.total_adj_credit || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 });

    if (balanceCheckEl) {
      const isBalanced = Math.abs((summary.total_adj_debit || 0) - (summary.total_adj_credit || 0)) < 0.01;
      if (isBalanced) {
        balanceCheckEl.innerHTML = `
          <div class="balance-check balanced" style="margin-bottom: 20px;">
            <span>✓</span> Adjustments are in balance.
          </div>
        `;
      } else {
        const diff = Math.abs((summary.total_adj_debit || 0) - (summary.total_adj_credit || 0));
        balanceCheckEl.innerHTML = `
          <div class="balance-check unbalanced" style="margin-bottom: 20px;">
            <span>✗</span> Adjustments are unbalanced by ${diff.toLocaleString('en-IN', { minimumFractionDigits: 2 })}.
          </div>
        `;
      }
    }
  }

  function renderTable() {
    const container = document.getElementById('adj-tb-table-container');
    if (!container) return;

    if (ledgers.length === 0) {
      container.innerHTML = `
        <div class="stat-card" style="text-align: center; padding: 48px;">
          <div style="font-size: 14px; color: var(--text-muted);">No ledger entries found.</div>
        </div>
      `;
      return;
    }

    // Pagination
    const totalPages = Math.ceil(ledgers.length / limit);
    if (currentPage > totalPages) currentPage = totalPages || 1;
    const start = (currentPage - 1) * limit;
    const end = start + limit;
    const sliced = ledgers.slice(start, end);

    const fmt = (v) => v ? v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';

    const rowsHtml = sliced.map(l => {
      const hasAdj = l.has_adjustment || (l.adj_debit !== 0 || l.adj_credit !== 0);
      const rowClass = hasAdj ? 'has-adjustment' : '';
      const netAdj = l.adj_debit - l.adj_credit;
      const netAdjLabel = netAdj !== 0 ? (netAdj > 0 ? `+${fmt(netAdj)}` : fmt(netAdj)) : '—';

      return `
        <tr class="${rowClass}">
          <td class="mono">${window.AE.escapeHtml(l.ledger_code)}</td>
          <td>
            ${window.AE.escapeHtml(l.ledger_name)}
            ${l.subgroup_name ? `<div style="font-size:10px; color:var(--text-muted); margin-top:2px;">${window.AE.escapeHtml(l.group_name)} &gt; ${window.AE.escapeHtml(l.subgroup_name)}</div>` : ''}
          </td>
          <td class="text-right mono">${fmt(l.closing_balance)}</td>
          <td class="text-right mono">${l.adj_debit > 0 ? fmt(l.adj_debit) : '—'}</td>
          <td class="text-right mono">${l.adj_credit > 0 ? fmt(l.adj_credit) : '—'}</td>
          <td class="text-right mono" style="font-weight: 600;">${fmt(l.adjusted_closing)}</td>
          <td style="font-size:11px; color:var(--text-muted); text-align: left;">
            ${window.AE.escapeHtml(l.entry_references || '')}
          </td>
        </tr>
      `;
    }).join('');

    const totalsRowHtml = `
      <tr style="font-weight: 700; background: var(--bg-raised);">
        <td colspan="2">TOTAL</td>
        <td class="text-right mono">${fmt(summary.total_closing)}</td>
        <td class="text-right mono">${fmt(summary.total_adj_debit)}</td>
        <td class="text-right mono">${fmt(summary.total_adj_credit)}</td>
        <td class="text-right mono">${fmt(summary.total_adjusted_closing)}</td>
        <td></td>
      </tr>
    `;

    container.innerHTML = `
      <table class="adj-tb-table">
        <thead>
          <tr>
            <th>Ledger Code</th>
            <th>Ledger Name</th>
            <th class="text-right">Original Closing</th>
            <th class="text-right">Debit Adj</th>
            <th class="text-right">Credit Adj</th>
            <th class="text-right">Adjusted Closing</th>
            <th style="text-align: left;">Entry Refs</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
          ${totalsRowHtml}
        </tbody>
      </table>
    `;

    renderPaginationControls(totalPages);
  }

  function renderPaginationControls(totalPages) {
    const pag = document.getElementById('adj-tb-pagination');
    if (!pag) return;

    if (totalPages <= 1) {
      pag.innerHTML = '';
      return;
    }

    let btns = `<button ${currentPage === 1 ? 'disabled' : ''} data-page="${currentPage - 1}">&larr; Prev</button>`;
    for (let i = 1; i <= totalPages; i++) {
      btns += `<button class="${currentPage === i ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    btns += `<button ${currentPage === totalPages ? 'disabled' : ''} data-page="${currentPage + 1}">Next &rarr;</button>`;

    pag.innerHTML = btns;

    pag.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        currentPage = parseInt(btn.dataset.page);
        renderTable();
      });
    });
  }

  async function approveAdjustedTB() {
    if (!confirm('Are you sure you want to approve the Adjusted Trial Balance? This will lock adjustments for report preparation.')) return;

    const btn = document.getElementById('btn-approve-adj-tb');
    if (btn) btn.disabled = true;

    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/adjusted-tb/approve`, {
        method: 'POST'
      });

      if (res.ok) {
        alert('Adjusted Trial Balance Approved successfully.');
        window.location.href = `/audit/financials.html?id=${engagementId}`;
      } else {
        alert('Failed to approve Adjusted Trial Balance.');
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      console.error(e);
      alert('Network error approving Adjusted Trial Balance.');
      if (btn) btn.disabled = false;
    }
  }
})();
