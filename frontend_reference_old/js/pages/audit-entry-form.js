/* =====================================================================
   audit-entry-form.js — Create/Edit Audit Entry logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'Audit Entry Form';
  const PAGE_URL = '/audit/entry-form.html';

  let engagementId = null;
  let entryId = null;
  let ledgers = [];

  // State for lines
  let debits = [];
  let credits = [];
  let nextRowId = 1;

  document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    engagementId = urlParams.get('id');
    entryId = urlParams.get('eid');

    if (!engagementId) {
      alert('No engagement ID specified.');
      window.location.href = '/audit/index.html';
      return;
    }

    window.AE.initTopbar({ showBack: true, backHref: `/audit/entries.html?id=${engagementId}` });
    window.AE.initSidebar(PAGE_KEY);
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, `${PAGE_URL}?id=${engagementId}${entryId ? `&eid=${entryId}` : ''}`);

    // Update subnav links
    const subnav = document.getElementById('audit-subnav');
    if (subnav) {
      subnav.querySelectorAll('a').forEach(link => {
        const page = link.getAttribute('href').split('?')[0];
        link.setAttribute('href', `${page}?id=${engagementId}`);
      });
    }

    // Set page cancel link
    document.getElementById('btn-cancel-entry')?.setAttribute('href', `/audit/entries.html?id=${engagementId}`);

    // Load trial balance ledgers for search dropdowns
    await loadLedgers();

    // Type cards selection styling
    const cards = document.querySelectorAll('.entry-type-selector .entry-type-card');
    cards.forEach(card => {
      card.addEventListener('click', () => {
        cards.forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
      });
    });

    // Add buttons
    document.getElementById('btn-add-debit')?.addEventListener('click', () => addLine('debit'));
    document.getElementById('btn-add-credit')?.addEventListener('click', () => addLine('credit'));

    // Save buttons
    document.getElementById('btn-save-draft')?.addEventListener('click', () => saveEntry('Draft'));
    document.getElementById('btn-submit-entry')?.addEventListener('click', () => saveEntry('Submitted'));

    if (entryId) {
      document.getElementById('entry-form-title').textContent = 'Edit Audit Entry';
      await loadEntryDetails();
    } else {
      // Default: start with 1 debit and 1 credit line
      addLine('debit');
      addLine('credit');
      // Set today's date by default
      const dateEl = document.getElementById('entry-date');
      if (dateEl) dateEl.value = new Date().toISOString().split('T')[0];
    }
  });

  async function loadLedgers() {
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/trial-balance`);
      if (res.ok) {
        const data = await res.json();
        ledgers = data.ledgers || [];
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function loadEntryDetails() {
    try {
      const res = await window.AE.apiFetch(`/api/audit/${engagementId}/entries/${entryId}`);
      if (res.ok) {
        const entry = await res.json();

        // Populate details
        const descEl = document.getElementById('entry-ref');
        if (descEl) descEl.value = entry.description || '';

        const dateEl = document.getElementById('entry-date');
        if (dateEl) dateEl.value = entry.entry_date || '';

        const narrationEl = document.getElementById('entry-narration');
        if (narrationEl) narrationEl.value = entry.narration || '';

        // Populate lines
        const debitLines = entry.lines.filter(l => l.line_type === 'debit');
        const creditLines = entry.lines.filter(l => l.line_type === 'credit');

        debitLines.forEach(l => addLine('debit', l.ledger_id, l.amount));
        creditLines.forEach(l => addLine('credit', l.ledger_id, l.amount));

        updateBalances();
      }
    } catch (e) {
      console.error(e);
      alert('Error loading entry details.');
    }
  }

  function addLine(side, ledgerId = null, amount = '') {
    const listId = side === 'debit' ? 'debit-lines' : 'credit-lines';
    const container = document.getElementById(listId);
    if (!container) return;

    const rowId = nextRowId++;
    const row = document.createElement('div');
    row.className = 'entry-line-row';
    row.id = `row-${rowId}`;

    row.innerHTML = `
      <div class="searchable-select" id="select-container-${rowId}">
        <input type="text" class="input searchable-select-input" id="select-input-${rowId}" placeholder="Search ledger..." readonly />
        <div class="searchable-select-dropdown" id="select-dropdown-${rowId}">
          <input type="text" class="input select-search-input" id="select-search-${rowId}" placeholder="Type to filter..." style="padding: 4px 8px; margin: 4px; width: calc(100% - 8px);" />
          <div class="options-list" id="select-options-${rowId}" style="max-height: 160px; overflow-y: auto;">
            <!-- Options populated dynamically -->
          </div>
        </div>
        <input type="hidden" id="ledger-id-${rowId}" value="${ledgerId || ''}" />
      </div>
      <div>
        <input type="number" class="input line-amount" id="amount-${rowId}" placeholder="Amount" step="0.01" min="0.01" value="${amount}" required style="text-align: right;" />
      </div>
      <div>
        <button type="button" class="btn-delete-line" style="background:transparent; border:none; cursor:pointer; font-size:16px; color:var(--status-action);" title="Delete line">🗑️</button>
      </div>
    `;

    container.appendChild(row);

    // Setup searchable dropdown logic
    setupSearchableSelect(rowId);

    // Amount change updates
    const amtInput = row.querySelector('.line-amount');
    amtInput.addEventListener('input', updateBalances);

    // Delete row action
    row.querySelector('.btn-delete-line').addEventListener('click', () => {
      row.remove();
      updateBalances();
    });

    // Update balances
    updateBalances();
  }

  function setupSearchableSelect(rowId) {
    const container = document.getElementById(`select-container-${rowId}`);
    const input = document.getElementById(`select-input-${rowId}`);
    const dropdown = document.getElementById(`select-dropdown-${rowId}`);
    const search = document.getElementById(`select-search-${rowId}`);
    const optionsList = document.getElementById(`select-options-${rowId}`);
    const hiddenInput = document.getElementById(`ledger-id-${rowId}`);

    // If predefined ledgerId is passed, set initial text
    if (hiddenInput.value) {
      const ledg = ledgers.find(l => l.id === parseInt(hiddenInput.value));
      if (ledg) {
        input.value = `[${ledg.ledger_code}] ${ledg.ledger_name}`;
      }
    }

    input.addEventListener('click', (e) => {
      e.stopPropagation();
      // Close other dropdowns
      document.querySelectorAll('.searchable-select-dropdown').forEach(d => {
        if (d.id !== `select-dropdown-${rowId}`) d.classList.remove('open');
      });
      dropdown.classList.toggle('open');
      if (dropdown.classList.contains('open')) {
        search.focus();
        renderOptions('');
      }
    });

    search.addEventListener('input', (e) => {
      renderOptions(e.target.value);
    });

    // Close when clicking outside
    document.addEventListener('click', (e) => {
      if (!container.contains(e.target)) {
        dropdown.classList.remove('open');
      }
    });

    function renderOptions(query) {
      const q = query.toLowerCase().trim();
      const filtered = ledgers.filter(l =>
        l.ledger_code.toLowerCase().includes(q) ||
        l.ledger_name.toLowerCase().includes(q)
      );

      if (filtered.length === 0) {
        optionsList.innerHTML = `<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center;">No match found</div>`;
        return;
      }

      optionsList.innerHTML = filtered.map(l => `
        <div class="searchable-select-option" data-id="${l.id}">
          <span class="ledger-code">[${window.AE.escapeHtml(l.ledger_code)}]</span>
          <span class="ledger-name">${window.AE.escapeHtml(l.ledger_name)}</span>
        </div>
      `).join('');

      optionsList.querySelectorAll('.searchable-select-option').forEach(opt => {
        opt.addEventListener('click', () => {
          const id = opt.dataset.id;
          hiddenInput.value = id;
          const ledg = ledgers.find(l => l.id === parseInt(id));
          input.value = ledg ? `[${ledg.ledger_code}] ${ledg.ledger_name}` : '';
          dropdown.classList.remove('open');
          updateBalances();
        });
      });
    }
  }

  function getLinesData() {
    const list = [];
    document.querySelectorAll('.entry-line-row').forEach(row => {
      const rowId = row.id.split('-')[1];
      const ledgerId = parseInt(document.getElementById(`ledger-id-${rowId}`)?.value || 0);
      const amount = parseFloat(document.getElementById(`amount-${rowId}`)?.value || 0);
      const isDebit = row.parentNode.id === 'debit-lines';

      if (ledgerId && amount > 0) {
        list.push({
          ledger_id: ledgerId,
          line_type: isDebit ? 'debit' : 'credit',
          amount: amount
        });
      }
    });
    return list;
  }

  function updateBalances() {
    const lines = getLinesData();
    const debitsList = lines.filter(l => l.line_type === 'debit');
    const creditsList = lines.filter(l => l.line_type === 'credit');

    const totalDebit = debitsList.reduce((s, l) => s + l.amount, 0);
    const totalCredit = creditsList.reduce((s, l) => s + l.amount, 0);

    const debitEl = document.getElementById('total-debit');
    const creditEl = document.getElementById('total-credit');
    const statusEl = document.getElementById('balance-status');

    if (debitEl) debitEl.textContent = totalDebit.toLocaleString('en-IN', { minimumFractionDigits: 2 });
    if (creditEl) creditEl.textContent = totalCredit.toLocaleString('en-IN', { minimumFractionDigits: 2 });

    const isBalanced = Math.abs(totalDebit - totalCredit) < 0.01;

    if (statusEl) {
      if (isBalanced && totalDebit > 0) {
        statusEl.className = 'balanced';
        statusEl.textContent = 'Balanced ✓';
      } else {
        statusEl.className = 'unbalanced';
        const diff = Math.abs(totalDebit - totalCredit);
        statusEl.textContent = `Unbalanced (Diff: ${diff.toLocaleString('en-IN', { minimumFractionDigits: 2 })})`;
      }
    }
  }

  async function saveEntry(status) {
    const description = document.getElementById('entry-ref')?.value?.trim();
    const entry_date = document.getElementById('entry-date')?.value;
    const narration = document.getElementById('entry-narration')?.value?.trim() || '';

    if (!description || !entry_date) {
      alert('Description/Reference and Date are required.');
      return;
    }

    const lines = getLinesData();
    const debitsList = lines.filter(l => l.line_type === 'debit');
    const creditsList = lines.filter(l => l.line_type === 'credit');

    if (debitsList.length === 0 || creditsList.length === 0) {
      alert('Must have at least 1 Debit and 1 Credit line.');
      return;
    }

    // Determine structural type constraints
    let entry_type = '';
    if (debitsList.length === 1 && creditsList.length === 1) {
      entry_type = 'one_to_one';
    } else if (debitsList.length === 1 && creditsList.length >= 2) {
      entry_type = 'one_to_many';
    } else if (debitsList.length >= 2 && creditsList.length >= 2) {
      entry_type = 'many_to_many';
    } else {
      alert('Invalid entry structure. Supported: 1:1, 1:N, or N:N Debit/Credit lines.');
      return;
    }

    // Balance check validation
    const totalDebit = debitsList.reduce((s, l) => s + l.amount, 0);
    const totalCredit = creditsList.reduce((s, l) => s + l.amount, 0);
    if (Math.abs(totalDebit - totalCredit) >= 0.01) {
      alert('Debits and Credits are unbalanced.');
      return;
    }

    const payload = {
      entry_type,
      description,
      narration,
      entry_date,
      lines
    };

    const saveBtn = document.getElementById('btn-save-draft');
    const submitBtn = document.getElementById('btn-submit-entry');

    if (saveBtn) saveBtn.disabled = true;
    if (submitBtn) submitBtn.disabled = true;

    try {
      const url = entryId
        ? `/api/audit/${engagementId}/entries/${entryId}`
        : `/api/audit/${engagementId}/entries`;
      const method = entryId ? 'PATCH' : 'POST';

      const res = await window.AE.apiFetch(url, {
        method,
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const entryResult = await res.json();
        // If status is 'Submitted', post to submit
        if (status === 'Submitted') {
          await window.AE.apiFetch(`/api/audit/${engagementId}/entries/${entryResult.id}/submit`, {
            method: 'POST'
          });
        }
        window.location.href = `/audit/entries.html?id=${engagementId}`;
      } else {
        const errorData = await res.json().catch(() => ({}));
        alert(errorData.error || 'Failed to save audit entry.');
        if (saveBtn) saveBtn.disabled = false;
        if (submitBtn) submitBtn.disabled = false;
      }
    } catch (err) {
      console.error(err);
      alert('Network error saving entry.');
      if (saveBtn) saveBtn.disabled = false;
      if (submitBtn) submitBtn.disabled = false;
    }
  }
})();
