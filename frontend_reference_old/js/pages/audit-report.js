/* =====================================================================
   audit-report.js — Annual Report Generator logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Annual Report';
  const PAGE_URL = '/audit/report.html';

  let engagementId = null;
  let previewData = null;
  let selectedTemplateType = 'standard'; // 'standard', 'detailed', 'summary'

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

    // Template selection cards
    const cards = document.querySelectorAll('.entry-type-card');
    cards.forEach(card => {
      card.addEventListener('click', () => {
        cards.forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        selectedTemplateType = card.dataset.template || 'standard';
        renderReportPreview();
      });
    });

    document.getElementById('btn-generate-report')?.addEventListener('click', generateReport);

    await loadReportPreview();
  });

  async function loadReportPreview() {
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/report/preview`);
      if (res.ok) {
        previewData = await res.json();
        renderReportPreview();
      }
    } catch (e) {
      console.error(e);
      showError('Error loading report preview.');
    }
  }

  const fmt = (v) => (v !== undefined && v !== null) ? v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';

  function renderReportPreview() {
    const previewContainer = document.getElementById('report-preview');
    if (!previewContainer || !previewData) return;

    const eng = previewData.engagement || {};
    const bs = previewData.balance_sheet || {};
    const pnl = previewData.profit_and_loss || {};

    const isProfit = (pnl.summary?.net_profit || 0) >= 0;

    let detailsHtml = '';

    if (selectedTemplateType === 'standard' || selectedTemplateType === 'detailed') {
      detailsHtml = `
        <div style="margin-top: 16px; border-top: 1px solid var(--border); padding-top: 12px;">
          <h4 style="font-size:13px; margin:0 0 8px; color:var(--text-primary);">Financial Snapshot</h4>
          <table style="width:100%; font-size:12px; border-collapse:collapse;">
            <tr>
              <td style="padding:4px 0; color:var(--text-secondary);">Total Assets:</td>
              <td style="padding:4px 0; text-align:right; font-weight:600; font-family:monospace;">${fmt(bs.summary?.total_assets)}</td>
            </tr>
            <tr>
              <td style="padding:4px 0; color:var(--text-secondary);">Liabilities &amp; Equity:</td>
              <td style="padding:4px 0; text-align:right; font-weight:600; font-family:monospace;">${fmt(bs.summary?.liabilities_plus_equity)}</td>
            </tr>
            <tr>
              <td style="padding:4px 0; color:var(--text-secondary);">Total Revenues:</td>
              <td style="padding:4px 0; text-align:right; font-weight:600; font-family:monospace;">${fmt(pnl.summary?.total_income)}</td>
            </tr>
            <tr>
              <td style="padding:4px 0; color:var(--text-secondary);">Net Profit / (Loss):</td>
              <td style="padding:4px 0; text-align:right; font-weight:600; font-family:monospace; color:${isProfit ? 'var(--status-verified)' : 'var(--status-action)'}">${fmt(pnl.summary?.net_profit)}</td>
            </tr>
          </table>
        </div>
      `;
    }

    if (selectedTemplateType === 'detailed') {
      detailsHtml += `
        <div style="margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 8px; font-size:11px; color:var(--text-muted);">
          * Detailed mode includes ledger-level schedules appended to the report.
        </div>
      `;
    }

    previewContainer.innerHTML = `
      <div class="report-section" style="text-align: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 16px;">
        <h2 style="font-size: 18px; margin: 0; color: var(--text-primary); font-weight: 700;">INDEPENDENT AUDITOR'S REPORT</h2>
        <p style="font-size:13px; color:var(--text-secondary); margin: 6px 0 0 0;">
          To the Members of <strong>${window.AE.escapeHtml(eng.client_name)}</strong>
        </p>
      </div>

      <div class="report-section">
        <h3 style="font-size:14px; color:var(--text-primary); margin-bottom:8px;">1. Opinion</h3>
        <p style="font-size:13px; color:var(--text-secondary); line-height:1.6; margin:0;">
          We have audited the financial statements of <strong>${window.AE.escapeHtml(eng.client_name)}</strong>, which comprise the Balance Sheet as of ${eng.period_end || 'Reporting Date'}, and the Statement of Profit and Loss for the year then ended, and notes to the financial statements, including a summary of significant accounting policies.
        </p>
      </div>

      <div class="report-section" style="margin-top: 16px;">
        <h3 style="font-size:14px; color:var(--text-primary); margin-bottom:8px;">2. Basis for Opinion</h3>
        <p style="font-size:13px; color:var(--text-secondary); line-height:1.6; margin:0;">
          We conducted our audit in accordance with the Standards on Auditing. Our responsibilities under those Standards are further described in the Auditor's Responsibilities for the Audit of the Financial Statements section of our report.
        </p>
      </div>

      ${detailsHtml}
    `;
  }

  async function generateReport() {
    const btn = document.getElementById('btn-generate-report');
    if (btn) btn.disabled = true;

    try {
      // 1. Fetch templates to see if we have one, or pass null
      let template_id = null;
      try {
        const tplRes = await window.AE.apiFetch('/api/audit/templates');
        if (tplRes.ok) {
          const templates = await tplRes.json();
          if (templates.length > 0) {
            template_id = templates[0].id;
          }
        }
      } catch (err) {
        console.error('Templates fetch error:', err);
      }

      // 2. Generate report
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/report/generate`, {
        method: 'POST',
        body: JSON.stringify({
          template_id: template_id,
          report_type: 'annual_report'
        })
      });

      if (res.ok) {
        const data = await res.json();
        alert('Annual Report generated, encrypted, and saved to Document Vault successfully!');
        
        // Show success state in preview
        const previewContainer = document.getElementById('report-preview');
        if (previewContainer) {
          previewContainer.innerHTML = `
            <div style="text-align:center; padding:32px;">
              <div style="font-size:48px; margin-bottom:16px;">🎉</div>
              <h3 style="color:var(--status-verified); margin:0 0 8px 0;">Report Compiled Successfully!</h3>
              <p style="font-size:13px; color:var(--text-secondary); margin:0 0 20px 0;">
                The document has been securely encrypted and stored in the <strong>Document Vault</strong>.
              </p>
              <div style="font-size:12px; color:var(--text-muted); background:var(--bg-raised); padding:10px; border-radius:4px; font-family:monospace; display:inline-block; text-align:left;">
                <strong>Document ID:</strong> ${data.document_id}<br/>
                <strong>Filename:</strong> ${window.AE.escapeHtml(data.stored_filename)}
              </div>
              <div style="margin-top:24px;">
                <a href="/documents/dashboard.html" class="btn btn-primary">Go to Document Vault</a>
              </div>
            </div>
          `;
        }

        // Change engagement status to complete
        try {
          await window.AE.apiFetch(`/api/audit/engagements/${engagementId}`, {
            method: 'PATCH',
            body: JSON.stringify({ status: 'Report Generated' })
          });
        } catch (e) {
          console.error('Failed to update engagement status:', e);
        }

      } else {
        const err = await res.json().catch(() => ({}));
        alert(err.error || 'Failed to generate report.');
        if (btn) btn.disabled = false;
      }
    } catch (e) {
      console.error(e);
      alert('Network error compiling report.');
      if (btn) btn.disabled = false;
    }
  }

  function showError(msg) {
    const previewContainer = document.getElementById('report-preview');
    if (previewContainer) {
      previewContainer.innerHTML = `
        <div style="text-align:center; padding:24px; color:var(--status-action);">
          ${window.AE.escapeHtml(msg)}
        </div>
      `;
    }
  }
})();
