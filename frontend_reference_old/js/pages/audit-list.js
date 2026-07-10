/* =====================================================================
   audit-list.js — Engagement list logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Audit Engagements';
  const PAGE_URL = '/audit/index.html';

  const PIPELINE_STEPS = [
    { key: 'Active',                   label: 'Active' },
    { key: 'Trial Balance Imported',   label: 'Import TB' },
    { key: 'Mapping Complete',         label: 'Map Ledgers' },
    { key: 'Entries In Progress',      label: 'Entries' },
    { key: 'Adjusted TB Approved',     label: 'Adjusted TB' },
    { key: 'Financials Approved',      label: 'Financials' },
    { key: 'Report Generated',         label: 'Report' },
  ];

  let engagements = [];

  document.addEventListener('DOMContentLoaded', async () => {
    window.AE.initTopbar({ showBack: false });
    window.AE.initSidebar(PAGE_KEY);
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, PAGE_URL);

    // Initialize list
    await loadEngagements();

    // Attach filters
    const searchInput = document.getElementById('search-engagements');
    const statusSelect = document.getElementById('filter-status');

    if (searchInput) searchInput.addEventListener('input', filterEngagements);
    if (statusSelect) statusSelect.addEventListener('change', filterEngagements);
  });

  async function loadEngagements() {
    try {
      const res = await window.AE.apiFetch('/api/audit/engagements');
      if (res.ok) {
        engagements = await res.json();
        renderEngagements(engagements);
      } else if (res.status === 401) {
        window.AE.showAuthGuard();
      } else {
        showError('Failed to load engagements.');
      }
    } catch (e) {
      console.error(e);
      showError('Network error loading engagements.');
    }
  }

  function getPipelineIndex(status) {
    return PIPELINE_STEPS.findIndex(s => s.key.toLowerCase() === status.toLowerCase());
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

  function renderEngagements(list) {
    const grid = document.getElementById('engagements-grid');
    if (!grid) return;

    if (list.length === 0) {
      grid.innerHTML = `
        <div class="stat-card" style="grid-column: 1 / -1; text-align: center; padding: 48px;">
          <div style="font-size: 14px; color: var(--text-muted);">No engagements found.</div>
          <a href="/audit/new.html" class="btn btn-primary" style="margin-top: 16px; display: inline-block;">Create your first Engagement</a>
        </div>
      `;
      return;
    }

    grid.innerHTML = list.map(eng => {
      const currentIdx = getPipelineIndex(eng.status);
      const statusLabel = eng.status || 'Active';

      const pipelineHtml = PIPELINE_STEPS.map((step, idx) => {
        let dotStyle = 'background: var(--bg-raised); border: 1px solid var(--border);';
        let stepClass = 'pending';
        if (idx < currentIdx) {
          stepClass = 'done';
          dotStyle = 'background: var(--status-verified);';
        } else if (idx === currentIdx) {
          stepClass = 'current';
          dotStyle = 'background: var(--accent);';
        }
        return `
          <div class="card-pipeline-step" style="display: flex; flex-direction: column; align-items: center; gap: 4px;" title="${window.AE.escapeHtml(step.label)}">
            <span style="font-size: 10px; font-weight: 600; color: var(--text-secondary);">${idx + 1}</span>
            <span style="width: 8px; height: 8px; border-radius: 50%; ${dotStyle}"></span>
          </div>
        `;
      }).join('<div style="flex: 1; height: 1px; background: var(--border); margin-top: 14px;"></div>');

      return `
        <div class="audit-card">
          <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <h3 style="margin: 0; font-size: 16px; font-weight: 600; color: var(--text-primary);">
              ${window.AE.escapeHtml(eng.client_name)}
            </h3>
            <span class="audit-status-badge badge-${getStatusBadgeClass(eng.status)}">
              ${window.AE.escapeHtml(statusLabel)}
            </span>
          </div>

          <div style="margin-top: 8px; font-size: 13px; color: var(--text-secondary);">
            <strong>Financial Year:</strong> ${window.AE.escapeHtml(eng.financial_year)}
          </div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
            ${formatDate(eng.period_start)} — ${formatDate(eng.period_end)}
          </div>

          <!-- Pipeline visualization -->
          <div class="card-pipeline" style="display: flex; align-items: center; justify-content: space-between; margin: 16px 0; background: var(--bg-raised); padding: 8px 12px; border-radius: 4px;">
            ${pipelineHtml}
          </div>

          <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px; font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: 12px;">
            <div>
              ${eng.ledger_count || 0} ledgers &middot; ${eng.entry_count || 0} entries
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <button class="btn btn-ghost btn-sm btn-delete-engagement" data-id="${eng.id}" data-name="${window.AE.escapeHtml(eng.client_name)} (${window.AE.escapeHtml(eng.financial_year)})" style="color: var(--status-action); padding: 4px 8px; cursor: pointer;" title="Delete engagement">🗑️</button>
              <a href="/audit/engagement.html?id=${eng.id}" class="btn btn-secondary btn-sm" style="text-decoration: none;">
                Open &rarr;
              </a>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Attach delete listeners
    grid.querySelectorAll('.btn-delete-engagement').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const id = btn.dataset.id;
        const name = btn.dataset.name;
        if (confirm(`Are you sure you want to delete the engagement "${name}"? This will permanently delete all associated ledgers, mappings, query replies, and audit entries. This action cannot be undone.`)) {
          try {
            const res = await window.AE.apiFetch(`/api/audit/engagements/${id}`, {
              method: 'DELETE'
            });
            if (res.ok) {
              await loadEngagements();
            } else {
              alert('Failed to delete engagement.');
            }
          } catch (err) {
            console.error(err);
            alert('Error deleting engagement.');
          }
        }
      });
    });
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

  function filterEngagements() {
    const searchVal = (document.getElementById('search-engagements')?.value || '').toLowerCase().trim();
    const statusVal = (document.getElementById('filter-status')?.value || '').toLowerCase();

    const filtered = engagements.filter(eng => {
      const matchesSearch = eng.client_name.toLowerCase().includes(searchVal) ||
                            eng.financial_year.toLowerCase().includes(searchVal);
      
      let matchesStatus = true;
      if (statusVal) {
        const engStatus = eng.status.toLowerCase();
        // If statusVal is "active", match "active" or standard
        if (statusVal === 'active') {
          matchesStatus = engStatus === 'active';
        } else if (statusVal === 'draft') {
          matchesStatus = engStatus.includes('draft');
        } else if (statusVal === 'submitted') {
          matchesStatus = engStatus.includes('imported') || engStatus.includes('progress') || engStatus.includes('submitted');
        } else if (statusVal === 'approved') {
          matchesStatus = engStatus.includes('approved') || engStatus.includes('complete') || engStatus.includes('generated');
        }
      }

      return matchesSearch && matchesStatus;
    });

    renderEngagements(filtered);
  }

  function showError(msg) {
    const grid = document.getElementById('engagements-grid');
    if (grid) {
      grid.innerHTML = `
        <div class="stat-card" style="grid-column: 1 / -1; border-color: var(--status-action); text-align: center; padding: 24px;">
          <div style="color: var(--status-action); font-weight: 500;">${window.AE.escapeHtml(msg)}</div>
        </div>
      `;
    }
  }
})();
