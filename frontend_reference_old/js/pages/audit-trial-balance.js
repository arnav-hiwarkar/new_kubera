/* =====================================================================
   audit-trial-balance.js — Trial Balance Import and View logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Trial Balance';
  const PAGE_URL = '/audit/trial-balance.html';

  let engagementId = null;

  // ── Import Wizard State ─────────────────────────────────────────────
  let importState = {
    file: null,
    allSheetNames: [],
    selectedSheet: null,
    headerRowIndex: null,
    rawPreviewRows: [],
    columns: [],
    previewRows: [],
    columnMap: {
      ledger_code: null, ledger_name: null, opening_balance: null,
      debit_transactions: null, credit_transactions: null, closing_balance: null
    },
    manualSkipRows: new Set() // indices within previewRows the user explicitly excludes
  };

  const FIELD_LABELS = {
    ledger_code: 'Ledger Code', ledger_name: 'Ledger Name', opening_balance: 'Opening Balance',
    debit_transactions: 'Debit Transactions', credit_transactions: 'Credit Transactions', closing_balance: 'Closing Balance'
  };

  const REQUIRED_MAPPING_FIELDS = [
    'opening_balance', 'debit_transactions', 'credit_transactions', 'closing_balance'
  ];

  function autoDetectColumn(columns, fieldKey) {
    const patterns = {
      ledger_code: /ledger\s*code|a\/?c\s*no|account\s*no|gl\s*code/i,
      ledger_name: /ledger.?name|particular|name|description/i,
      opening_balance: /open/i,
      debit_transactions: /debit/i,
      credit_transactions: /credit/i,
      closing_balance: /clos/i
    };
    const pattern = patterns[fieldKey];
    if (!pattern) return null;
    const match = columns.find(c => c.header && pattern.test(c.header));
    return match ? match.index : null;
  }

  // View state
  let ledgers = [];
  let tbTotals = {};
  let viewPage = 1;
  const viewLimit = 50;
  let viewSearch = '';
  let viewMappedFilter = 'all'; // 'all', 'mapped', 'unmapped'

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

    initTabs();
    initImportWizard();
    await loadViewTab();
  });

  // ── Tabs ─────────────────────────────────────────────────────────────
  function initTabs() {
    const tabImportBtn = document.getElementById('tab-btn-import');
    const tabViewBtn = document.getElementById('tab-btn-view');
    const tabImportContent = document.getElementById('tab-import');
    const tabViewContent = document.getElementById('tab-view');

    tabImportBtn?.addEventListener('click', () => {
      tabImportBtn.classList.add('active');
      tabViewBtn.classList.remove('active');
      tabImportContent.style.display = 'block';
      tabViewContent.style.display = 'none';
    });

    tabViewBtn?.addEventListener('click', async () => {
      tabViewBtn.classList.add('active');
      tabImportBtn.classList.remove('active');
      tabViewContent.style.display = 'block';
      tabImportContent.style.display = 'none';
      await loadViewTab();
    });
  }

  // ── Import Wizard ───────────────────────────────────────────────────
  function initImportWizard() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('tb-file-input');

    // Click to open file picker
    dropZone?.addEventListener('click', () => fileInput?.click());

    // Drag-and-drop
    dropZone?.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });
    dropZone?.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone?.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        const file = e.dataTransfer.files[0];
        fileInput.files = e.dataTransfer.files;
        loadFilePreview(file);
      }
    });

    fileInput?.addEventListener('change', (e) => {
      if (e.target.files.length > 0) {
        loadFilePreview(e.target.files[0]);
      }
    });

    // Step 2 & 3 back/next buttons
    document.getElementById('btn-wizard-back-2')?.addEventListener('click', () => showStep(1));
    document.getElementById('mapping-back-btn')?.addEventListener('click', () => showStep(1));
    document.getElementById('mapping-continue-btn')?.addEventListener('click', proceedToStep3);
    document.getElementById('btn-wizard-back-3')?.addEventListener('click', () => showStep(2));
    document.getElementById('btn-confirm-import')?.addEventListener('click', executeImport);
  }

  function showStep(stepNum) {
    const steps = [1, 2, 3];
    steps.forEach(s => {
      const stepIndicator = document.querySelector(`.wizard-step[data-step="${s}"]`);
      const stepDiv = document.getElementById(`wizard-step-${s}`);
      if (s === stepNum) {
        stepIndicator?.classList.add('active');
        stepIndicator?.classList.remove('done');
        if (stepDiv) stepDiv.style.display = 'block';
      } else if (s < stepNum) {
        stepIndicator?.classList.remove('active');
        stepIndicator?.classList.add('done');
        if (stepDiv) stepDiv.style.display = 'none';
      } else {
        stepIndicator?.classList.remove('active', 'done');
        if (stepDiv) stepDiv.style.display = 'none';
      }
    });
  }

  // Step A — file selected: fetch sheet list + first preview using sheet[0], header guess
  async function loadFilePreview(file, sheetName = null, headerRowIndex = null) {
    importState.file = file;
    const engagementId = new URLSearchParams(window.location.search).get('id');

    const formData = new FormData();
    formData.append('file', file);
    if (sheetName) formData.append('sheet_name', sheetName);
    if (headerRowIndex !== null) formData.append('header_row_index', headerRowIndex);

    const res = await window.AE.apiFetch(`/api/audit/${engagementId}/trial-balance/preview`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok) { alert(data.error || 'Failed to read file.'); return; }

    importState.allSheetNames = data.all_sheet_names;
    importState.selectedSheet = data.selected_sheet;
    importState.headerRowIndex = data.header_row_index;
    importState.rawPreviewRows = data.raw_preview_rows;
    importState.columns = data.columns;
    importState.previewRows = data.preview_rows;

    renderSheetSelector();
    renderRawRowPicker();

    // If we already have a confirmed header row with real columns, show mapper too
    if (data.columns.some(c => c.header)) {
      Object.keys(FIELD_LABELS).forEach(f => {
        importState.columnMap[f] = autoDetectColumn(data.columns, f);
      });
      document.getElementById('column-mapping-section').style.display = 'block';
      renderColumnMapper();
      renderMappingPreview();
    } else {
      document.getElementById('column-mapping-section').style.display = 'none';
    }

    showStep(2);
    validateContinueButton();
  }

  function renderSheetSelector() {
    const select = document.getElementById('sheet-select');
    if (!select) return;
    
    // Check if we need to render or just update selection
    if (select.children.length === 0 || select.dataset.sheets !== JSON.stringify(importState.allSheetNames)) {
      select.innerHTML = '';
      select.dataset.sheets = JSON.stringify(importState.allSheetNames);
      importState.allSheetNames.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        if (name === importState.selectedSheet) opt.selected = true;
        select.appendChild(opt);
      });
    } else {
      select.value = importState.selectedSheet;
    }
  }

  document.getElementById('sheet-select')?.addEventListener('change', (e) => {
    // Re-preview from scratch on the new sheet — header row guess resets
    loadFilePreview(importState.file, e.target.value, null);
  });

  // Step B — show raw rows, let user click to mark header row
  function renderRawRowPicker() {
    const tbody = document.getElementById('raw-row-picker-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    importState.rawPreviewRows.forEach((row, idx) => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      if (idx === importState.headerRowIndex) {
        tr.style.background = 'var(--accent-subtle)';
        tr.style.outline = '2px solid var(--accent)';
      }

      const cells = row.map(cell => `<td>${window.AE.escapeHtml(String(cell ?? ''))}</td>`).join('');
      tr.innerHTML = `<td style="font-family:monospace;color:var(--text-muted);">Row ${idx + 1}</td>${cells}`;

      tr.addEventListener('click', () => {
        loadFilePreview(importState.file, importState.selectedSheet, idx);
      });

      tbody.appendChild(tr);
    });
  }

  // Step C — column mapper (same approach as before, but using real headers from chosen row)
  function renderColumnMapper() {
    const container = document.getElementById('column-mapper');
    if (!container) return;
    container.innerHTML = '';

    Object.entries(FIELD_LABELS).forEach(([fieldKey, fieldLabel]) => {
      const isRequired = REQUIRED_MAPPING_FIELDS.includes(fieldKey);
      const row = document.createElement('div');
      row.className = 'column-mapper-row';
      row.style.cssText = 'display:grid; grid-template-columns:200px 1fr; gap:12px; align-items:center; margin-bottom:10px;';

      const label = document.createElement('label');
      label.textContent = isRequired ? `${fieldLabel} *` : `${fieldLabel} (optional)`;
      label.style.cssText = 'font-size:13px;color:var(--text-secondary);';

      const select = document.createElement('select');
      select.dataset.field = fieldKey;
      select.style.cssText = 'padding:8px 10px;border:1px solid var(--border);border-radius:4px;background:var(--bg-surface);color:var(--text-primary);width:100%;';

      const emptyOpt = document.createElement('option');
      emptyOpt.value = '';
      emptyOpt.textContent = '— Select a column —';
      select.appendChild(emptyOpt);

      importState.columns.forEach(col => {
        const opt = document.createElement('option');
        opt.value = col.index;
        opt.textContent = col.label;
        if (importState.columnMap[fieldKey] === col.index) opt.selected = true;
        select.appendChild(opt);
      });

      select.addEventListener('change', (e) => {
        importState.columnMap[fieldKey] = e.target.value === '' ? null : parseInt(e.target.value, 10);
        renderMappingPreview();
        validateContinueButton();
      });

      row.appendChild(label);
      row.appendChild(select);
      container.appendChild(row);
    });
  }

  // Step D — live preview, now also flags rows that will be SKIPPED (blank ledger code)
  function renderMappingPreview() {
    const tbody = document.getElementById('mapping-preview-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    const map = importState.columnMap;
    let blankCount = 0;

    importState.previewRows.slice(0, 10).forEach((row, idx) => {
      const getVal = (fieldIdx) => fieldIdx !== null && fieldIdx !== undefined ? (row[fieldIdx] ?? '') : '';
      const code = getVal(map.ledger_code);
      const name = getVal(map.ledger_name);

      const codeWasMapped = map.ledger_code !== null && map.ledger_code !== undefined;
      const nameWasMapped = map.ledger_name !== null && map.ledger_name !== undefined;

      let willImport = true;
      let statusText = '✓ Import';

      if (codeWasMapped && String(code).trim() === '') {
        willImport = false;
        statusText = '— Skip (no ledger code)';
        blankCount++;
      } else if (nameWasMapped && String(name).trim() === '') {
        willImport = false;
        statusText = '— Skip (no ledger name)';
      }

      const tr = document.createElement('tr');
      if (!willImport) tr.style.opacity = '0.45';

      tr.innerHTML = `
        <td>${window.AE.escapeHtml(String(code))}</td>
        <td>${window.AE.escapeHtml(String(name))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.opening_balance)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.debit_transactions)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.credit_transactions)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.closing_balance)))}</td>
        <td>${statusText}</td>
      `;
      tbody.appendChild(tr);
    });

    const note = document.getElementById('skip-summary-note');
    if (note) {
      note.textContent = blankCount > 0
        ? `${blankCount} of the previewed rows have no ledger code and will be treated as group/subtotal rows — they will be skipped automatically.`
        : '';
    }
  }

  function validateContinueButton() {
    const map = importState.columnMap;
    const allRequiredMapped = REQUIRED_MAPPING_FIELDS.every(f => map[f] !== null);
    const values = Object.values(map).filter(v => v !== null);
    const noDuplicates = new Set(values).size === values.length;

    const errorEl = document.getElementById('mapping-validation-error');
    const btn = document.getElementById('mapping-continue-btn');
    if (!btn) return;

    if (!document.getElementById('column-mapping-section') || document.getElementById('column-mapping-section').style.display === 'none') {
        if(errorEl) errorEl.style.display = 'none';
        btn.disabled = true;
        return;
    }

    if (!allRequiredMapped) {
      const missing = REQUIRED_MAPPING_FIELDS.filter(f => map[f] === null).map(f => FIELD_LABELS[f]);
      if (errorEl) {
        errorEl.textContent = `Please map: ${missing.join(', ')}`;
        errorEl.style.display = 'block';
      }
      btn.disabled = true;
      return;
    }
    if (!noDuplicates) {
      if (errorEl) {
        errorEl.textContent = 'Each column can only be mapped to one field.';
        errorEl.style.display = 'block';
      }
      btn.disabled = true;
      return;
    }
    if (errorEl) errorEl.style.display = 'none';
    btn.disabled = false;
  }

  // ── Proceed to Step 3: Preview & Confirm ────────────────────────────
  function proceedToStep3() {
    const table = document.getElementById('tb-preview-table');
    if (!table) return;

    const map = importState.columnMap;
    const allRows = importState.previewRows;

    const headersHtml = [
      'Ledger Code', 'Ledger Name', 'Opening Balance',
      'Debit Transactions', 'Credit Transactions', 'Closing Balance'
    ].map(h => `<th>${window.AE.escapeHtml(h)}</th>`).join('');

    const rowsHtml = allRows.slice(0, 10).map(row => {
      const getVal = (idx) => idx !== null && idx !== undefined ? (row[idx] ?? '') : '';
      return `<tr>
        <td>${window.AE.escapeHtml(String(getVal(map.ledger_code)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.ledger_name)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.opening_balance)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.debit_transactions)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.credit_transactions)))}</td>
        <td>${window.AE.escapeHtml(String(getVal(map.closing_balance)))}</td>
      </tr>`;
    }).join('');

    table.innerHTML = `<thead><tr>${headersHtml}</tr></thead><tbody>${rowsHtml}</tbody>`;

    // Compute client-side balance check from all preview rows
    const parseNum = (v) => {
      if (v === '' || v === null || v === undefined) return 0;
      const cleaned = String(v).replace(/[,₹\s]/g, '');
      const num = parseFloat(cleaned);
      return isNaN(num) ? 0 : num;
    };

    let debitSum = 0;
    let creditSum = 0;
    const codeNameCounts = {};
    const codeOnlyCounts = {};

    allRows.forEach(row => {
      const code = (map.ledger_code !== null && map.ledger_code !== undefined)
        ? String(row[map.ledger_code] ?? '').trim()
        : '';
      const name = (map.ledger_name !== null && map.ledger_name !== undefined)
        ? String(row[map.ledger_name] ?? '').trim()
        : '';

      const codeWasMapped = map.ledger_code !== null && map.ledger_code !== undefined;
      const nameWasMapped = map.ledger_name !== null && map.ledger_name !== undefined;

      // Match backend skip logic:
      if (codeWasMapped && !code) return;
      if (nameWasMapped && !name) return;

      debitSum += parseNum(row[map.debit_transactions]);
      creditSum += parseNum(row[map.credit_transactions]);

      if (codeWasMapped) {
        codeOnlyCounts[code] = (codeOnlyCounts[code] || 0) + 1;
      }
      if (codeWasMapped || nameWasMapped) {
        const key = `${code}|||${name}`;
        codeNameCounts[key] = (codeNameCounts[key] || 0) + 1;
      }
    });

    const isBalanced = Math.abs(debitSum - creditSum) < 0.01;
    const checkContainer = document.getElementById('balance-check-container');
    if (checkContainer) {
      const totalRows = importState.previewRows.length; // Approximate total rows in preview
      if (isBalanced) {
        checkContainer.innerHTML = `
          <div class="balance-check balanced">
            <span>✓</span> Balanced: Total Debits equal Total Credits (Analyzed ${totalRows} rows).
          </div>
        `;
      } else {
        const diff = Math.abs(debitSum - creditSum);
        checkContainer.innerHTML = `
          <div class="balance-check unbalanced">
            <span>✗</span> Unbalanced: Difference is ${diff.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.
          </div>
        `;
      }
    }

    const dupNoticeContainer = document.getElementById('duplicate-notice-container');
    if (dupNoticeContainer) {
      dupNoticeContainer.innerHTML = '';

      const codesReused = Object.entries(codeOnlyCounts)
        .filter(([_, count]) => count > 1)
        .map(([code, count]) => ({ code, count }));

      const trueDuplicates = Object.entries(codeNameCounts)
        .filter(([_, count]) => count > 1)
        .map(([key, count]) => {
          const [code, name] = key.split('|||');
          return { code, name, count };
        });

      if (codesReused.length > 0) {
        const notice = document.createElement('div');
        notice.className = 'balance-check';
        notice.style.background = 'rgba(59, 130, 246, 0.1)';
        notice.style.color = 'var(--accent)';
        notice.style.border = '1px solid rgba(59, 130, 246, 0.3)';

        const topCodes = codesReused
          .sort((a, b) => b.count - a.count)
          .slice(0, 5)
          .map(d => `${d.code} (×${d.count})`)
          .join(', ');

        notice.innerHTML = `
          ℹ️ ${codesReused.length} ledger codes are reused across multiple different accounts
          (e.g. ${topCodes}). This is common in Tally exports and each will be imported as a 
          separate ledger since the names differ.
        `;
        dupNoticeContainer.appendChild(notice);
      }

      if (trueDuplicates.length > 0) {
        const notice = document.createElement('div');
        notice.className = 'balance-check unbalanced';
        const list = trueDuplicates
          .map(d => `${d.code} — "${d.name}" (×${d.count})`)
          .join('; ');
        notice.innerHTML = `
          ⚠ ${trueDuplicates.length} rows have the exact same ledger code AND name appearing 
          more than once: ${list}. Their amounts will be summed together into a single ledger entry.
        `;
        dupNoticeContainer.appendChild(notice);
      }
    }

    showStep(3);
  }

  // ── Final Import ────────────────────────────────────────────────────
  async function executeImport() {
    const formData = new FormData();
    formData.append('file', importState.file);
    formData.append('sheet_name', importState.selectedSheet);
    formData.append('header_row_index', importState.headerRowIndex);
    formData.append('column_map', JSON.stringify(importState.columnMap));
    formData.append('skip_row_indices', JSON.stringify(Array.from(importState.manualSkipRows)));

    const confirmBtn = document.getElementById('btn-confirm-import');
    if (confirmBtn) confirmBtn.disabled = true;

    try {
      const engagementId = new URLSearchParams(window.location.search).get('id');
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/trial-balance/import`, {
        method: 'POST',
        body: formData
      });

      const data = await res.json();
      if (!res.ok) {
        alert(data.error || 'Import failed.');
        if (confirmBtn) confirmBtn.disabled = false;
        return;
      }
      
      showImportSuccess(data);
    } catch (e) {
      console.error('[Import Error]', e);
      alert('Network error during import.');
      if (confirmBtn) confirmBtn.disabled = false;
    }
  }

  function showImportSuccess(data) {
    const msg = [
      `${data.imported} ledger accounts imported successfully.`,
      data.skippedBlank > 0 ? `${data.skippedBlank} rows skipped (group/subtotal rows with no ledger code).` : '',
      data.skippedManual > 0 ? `${data.skippedManual} rows manually excluded.` : '',
      data.errors && data.errors.length > 0 ? `${data.errors.length} rows had errors — check the details below.` : '',
      `Balance check: ${data.isBalanced ? '✓ Balanced' : '✗ Out of balance'}`
    ].filter(Boolean).join('\n');
    
    alert(msg);
    // Switch to view tab
    document.getElementById('tab-btn-view')?.click();
  }

  // ── View Tab ────────────────────────────────────────────────────────
  async function loadViewTab() {
    try {
      let url = `/api/audit/${engagementId}/trial-balance?`;
      if (viewSearch) url += `search=${encodeURIComponent(viewSearch)}&`;
      if (viewMappedFilter !== 'all') url += `mapped=${viewMappedFilter}&`;

      const res = await window.AE.apiFetch(url);
      if (res.ok) {
        const data = await res.json();
        ledgers = data.ledgers || [];
        tbTotals = data.totals || {};
        renderBalanceStatusBar();
        renderViewTable();
      }
    } catch (e) {
      console.error('Error loading view tab:', e);
    }
  }

  function renderBalanceStatusBar() {
    const bar = document.getElementById('tb-balance-status');
    if (!bar) return;

    if (ledgers.length === 0) {
      bar.innerHTML = '';
      return;
    }

    const { debit_transactions, credit_transactions, is_balanced } = tbTotals;
    const diff = Math.abs(debit_transactions - credit_transactions);

    if (is_balanced) {
      bar.innerHTML = `
        <div class="balance-check balanced" style="margin-bottom: 20px;">
          <span>✓</span> Balanced: Total Debits equal Total Credits.
        </div>
      `;
    } else {
      bar.innerHTML = `
        <div class="balance-check unbalanced" style="margin-bottom: 20px;">
          <span>✗</span> Unbalanced: Debits / Credits mismatch by ${diff.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}.
        </div>
      `;
    }
  }

  function renderViewTable() {
    const container = document.getElementById('tb-table-container');
    if (!container) return;

    // Filter controls inside view tab header
    const filterHeaderHtml = `
      <div class="audit-filter-bar">
        <input type="text" class="input" id="tb-search" placeholder="Search by ledger name or code…" value="${window.AE.escapeHtml(viewSearch)}" />
        <div class="filter-chips">
          <span class="filter-chip ${viewMappedFilter === 'all' ? 'active' : ''}" data-filter="all">All</span>
          <span class="filter-chip ${viewMappedFilter === 'unmapped' ? 'active' : ''}" data-filter="unmapped">Unmapped</span>
          <span class="filter-chip ${viewMappedFilter === 'mapped' ? 'active' : ''}" data-filter="mapped">Mapped</span>
        </div>
      </div>
    `;

    if (ledgers.length === 0) {
      container.innerHTML = filterHeaderHtml + `
        <div class="stat-card" style="text-align: center; padding: 48px;">
          <div style="font-size: 14px; color: var(--text-muted);">No ledger data imported yet or matches filters.</div>
        </div>
      `;
      attachViewFilterListeners();
      return;
    }

    // Pagination slice
    const totalCount = ledgers.length;
    const totalPages = Math.ceil(totalCount / viewLimit);
    if (viewPage > totalPages) viewPage = totalPages || 1;
    const start = (viewPage - 1) * viewLimit;
    const end = start + viewLimit;
    const sliced = ledgers.slice(start, end);

    const fmt = (v) => v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    const rowsHtml = sliced.map(l => {
      const mappingLabel = l.subgroup_name
        ? `${l.group_name} &rarr; ${l.subgroup_name}`
        : `<span class="audit-status-badge badge-rejected" style="font-size: 10px;">Unmapped</span>`;

      return `
        <tr class="${l.is_mapped ? '' : 'unmapped-row'}">
          <td class="mono">${window.AE.escapeHtml(l.ledger_code ?? '')}</td>
          <td>${window.AE.escapeHtml(l.ledger_name ?? '')}</td>
          <td class="text-right mono">${fmt(l.opening_balance)}</td>
          <td class="text-right mono">${fmt(l.debit_transactions)}</td>
          <td class="text-right mono">${fmt(l.credit_transactions)}</td>
          <td class="text-right mono">${fmt(l.closing_balance)}</td>
          <td>${mappingLabel}</td>
        </tr>
      `;
    }).join('');

    const totalsRowHtml = `
      <tr style="font-weight: 700; background: var(--bg-raised);">
        <td colspan="2">TOTAL</td>
        <td class="text-right mono">${fmt(tbTotals.opening_balance || 0)}</td>
        <td class="text-right mono">${fmt(tbTotals.debit_transactions || 0)}</td>
        <td class="text-right mono">${fmt(tbTotals.credit_transactions || 0)}</td>
        <td class="text-right mono">${fmt(tbTotals.closing_balance || 0)}</td>
        <td></td>
      </tr>
    `;

    container.innerHTML = filterHeaderHtml + `
      <table class="audit-table">
        <thead>
          <tr>
            <th>Ledger Code</th>
            <th>Ledger Name</th>
            <th class="text-right">Opening Bal</th>
            <th class="text-right">Debits</th>
            <th class="text-right">Credits</th>
            <th class="text-right">Closing Bal</th>
            <th>Mapping Group</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
          ${totalsRowHtml}
        </tbody>
      </table>
    `;

    renderPaginationControls(totalPages);
    attachViewFilterListeners();
  }

  function renderPaginationControls(totalPages) {
    const pag = document.getElementById('tb-pagination');
    if (!pag) return;

    if (totalPages <= 1) {
      pag.innerHTML = '';
      return;
    }

    let btns = `<button ${viewPage === 1 ? 'disabled' : ''} data-page="${viewPage - 1}">&larr; Prev</button>`;
    for (let i = 1; i <= totalPages; i++) {
      btns += `<button class="${viewPage === i ? 'active' : ''}" data-page="${i}">${i}</button>`;
    }
    btns += `<button ${viewPage === totalPages ? 'disabled' : ''} data-page="${viewPage + 1}">Next &rarr;</button>`;

    pag.innerHTML = btns;

    pag.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const page = parseInt(btn.dataset.page);
        if (page) {
          viewPage = page;
          renderViewTable();
        }
      });
    });
  }

  function attachViewFilterListeners() {
    const search = document.getElementById('tb-search');
    search?.addEventListener('input', (e) => {
      viewSearch = e.target.value;
      viewPage = 1;
      // Debounce slightly if typing
      clearTimeout(window.tbSearchTimeout);
      window.tbSearchTimeout = setTimeout(loadViewTab, 300);
    });

    const chips = document.querySelectorAll('.filter-chips .filter-chip');
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        viewMappedFilter = chip.dataset.filter;
        viewPage = 1;
        loadViewTab();
      });
    });
  }
})();
