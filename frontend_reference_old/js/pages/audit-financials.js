/* =====================================================================
   audit-financials.js — Financial Statements logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Financial Statements';
  const PAGE_URL = '/audit/financials.html';

  let engagementId = null;
  let bsData = null;
  let pnlData = null;

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

    document.getElementById('btn-approve-financials')?.addEventListener('click', approveFinancials);

    initTabs();
    await loadFinancials();
  });

  function initTabs() {
    const tabBsBtn = document.getElementById('tab-btn-bs');
    const tabPnlBtn = document.getElementById('tab-btn-pnl');
    const tabBsContent = document.getElementById('tab-balance-sheet');
    const tabPnlContent = document.getElementById('tab-pnl');

    tabBsBtn?.addEventListener('click', () => {
      tabBsBtn.classList.add('active');
      tabPnlBtn.classList.remove('active');
      tabBsContent.style.display = 'block';
      tabPnlContent.style.display = 'none';
    });

    tabPnlBtn?.addEventListener('click', () => {
      tabPnlBtn.classList.add('active');
      tabBsBtn.classList.remove('active');
      tabPnlContent.style.display = 'block';
      tabBsContent.style.display = 'none';
    });
  }

  async function loadFinancials() {
    try {
      const [bsRes, pnlRes] = await Promise.all([
        window.AE.apiFetch(`/api/audit/${engagementId}/balance-sheet`),
        window.AE.apiFetch(`/api/audit/${engagementId}/pnl`)
      ]);

      if (bsRes.ok) bsData = await bsRes.json();
      if (pnlRes.ok) pnlData = await pnlRes.json();

      renderBalanceSheet();
      renderPnL();
    } catch (e) {
      console.error(e);
      alert('Error loading Financial Statements.');
    }
  }

  const fmt = (v) => (v !== undefined && v !== null) ? v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';

  function renderSection(sectionName, sectionData) {
    let html = `<div class="fs-section-title">${sectionName.toUpperCase()}</div>`;
    const subgroups = sectionData.subgroups || {};

    if (Object.keys(subgroups).length === 0) {
      html += `<div style="font-size:12px;color:var(--text-muted);padding:8px 0;font-style:italic;">No mapped ledgers.</div>`;
      return html;
    }

    for (const subKey in subgroups) {
      const sg = subgroups[subKey];
      html += `
        <div class="fs-group-row">
          <span>${window.AE.escapeHtml(sg.subgroup_name)}</span>
          <span class="fs-amount">${fmt(sg.total)}</span>
        </div>
      `;

      const subSubgroups = sg.subSubgroups || {};
      for (const ssgKey in subSubgroups) {
        const ssg = subSubgroups[ssgKey];
        if (ssg.sub_subgroup_name) {
          html += `
            <div class="fs-subgroup-row">
              <span>${window.AE.escapeHtml(ssg.sub_subgroup_name)}</span>
              <span class="fs-amount">${fmt(ssg.total)}</span>
            </div>
          `;
        }

        const ledgers = ssg.ledgers || [];
        ledgers.forEach(l => {
          html += `
            <div class="fs-ledger-row" style="padding-left: 32px;">
              <span>[${window.AE.escapeHtml(l.ledger_code)}] ${window.AE.escapeHtml(l.ledger_name)}</span>
              <span class="fs-amount">${fmt(l.adjusted_closing)}</span>
            </div>
          `;
        });
      }
    }

    html += `
      <div class="fs-total-row">
        <span>Total ${sectionName}</span>
        <span class="fs-amount">${fmt(sectionData.total)}</span>
      </div>
    `;

    return html;
  }

  function renderBalanceSheet() {
    const container = document.getElementById('fs-balance-sheet');
    if (!container || !bsData) return;

    let html = `
      <div class="fs-header">
        <h2>Balance Sheet</h2>
        <p>As at ${bsData.summary ? 'Reporting Date' : '—'}</p>
      </div>
    `;

    // Render Asset
    html += renderSection('Asset', bsData.Asset);

    // Render Liability
    html += renderSection('Liability', bsData.Liability);

    // Render Equity
    html += renderSection('Equity', bsData.Equity);

    // Retained earnings / current year net profit is part of retained equity
    const netIncome = bsData.summary.net_income;
    html += `
      <div class="fs-ledger-row" style="font-style:italic;">
        <span>Current Period Net Profit / (Loss)</span>
        <span class="fs-amount">${fmt(netIncome)}</span>
      </div>
    `;

    // Totals check
    const totalAssets = bsData.summary.total_assets;
    const liabEquityTotal = bsData.summary.liabilities_plus_equity;
    const isBalanced = bsData.summary.is_balanced;

    if (isBalanced) {
      html += `
        <div class="fs-check-row balanced" style="background: rgba(16, 185, 129, 0.1); color: var(--status-verified); border: 1px solid rgba(16, 185, 129, 0.3); margin-top:24px;">
          Assets (${fmt(totalAssets)}) = Liabilities &amp; Equity (${fmt(liabEquityTotal)}) &mdash; Balanced ✓
        </div>
      `;
    } else {
      const diff = Math.abs(totalAssets - liabEquityTotal);
      html += `
        <div class="fs-check-row unbalanced" style="background: rgba(239, 68, 68, 0.1); color: var(--status-action); border: 1px solid rgba(239, 68, 68, 0.3); margin-top:24px;">
          Assets (${fmt(totalAssets)}) &ne; Liabilities &amp; Equity (${fmt(liabEquityTotal)}) &mdash; Difference: ${fmt(diff)} ✗
        </div>
      `;
    }

    container.innerHTML = html;
  }

  function renderPnL() {
    const container = document.getElementById('fs-pnl');
    if (!container || !pnlData) return;

    let html = `
      <div class="fs-header">
        <h2>Profit &amp; Loss Statement</h2>
        <p>For the period ended</p>
      </div>
    `;

    // Render Income
    html += renderSection('Income', pnlData.Income);

    // Render Expenditure
    html += renderSection('Expenditure', pnlData.Expenditure);

    // Net profit
    const netProfit = pnlData.summary.net_profit;
    const isProfit = netProfit >= 0;

    html += `
      <div class="fs-total-row" style="margin-top: 24px; border-bottom: 3px double var(--border);">
        <span>Net ${isProfit ? 'Profit' : 'Loss'}</span>
        <span class="fs-amount" style="color: ${isProfit ? 'var(--status-verified)' : 'var(--status-action)'}; font-size:16px;">
          ${fmt(netProfit)}
        </span>
      </div>
    `;

    container.innerHTML = html;
  }

  async function approveFinancials() {
    if (!confirm('Are you sure you want to approve these financial statements? This will mark the numbers as final for audit report compilation.')) return;

    const btn = document.getElementById('btn-approve-financials');
    if (btn) btn.disabled = true;

    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/financials/approve`, {
        method: 'POST'
      });

      if (res.ok) {
        alert('Financial Statements Approved successfully.');
        window.location.href = `/audit/report.html?id=${engagementId}`;
      } else {
        alert('Failed to approve Financial Statements.');
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      console.error(e);
      alert('Network error approving Financial Statements.');
      if (btn) btn.disabled = false;
    }
  }
})();
