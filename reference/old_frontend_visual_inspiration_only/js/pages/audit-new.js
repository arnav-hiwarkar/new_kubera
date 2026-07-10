/* =====================================================================
   audit-new.js — New engagement form logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'audit';
  const PAGE_LABEL = 'New Engagement';
  const PAGE_URL = '/audit/new.html';

  async function loadAuditors() {
    const list = document.getElementById('auditors-list');
    if (!list) return;
    try {
      const res = await window.AE.apiFetch('/api/users/auditors');
      if (!res.ok) throw new Error();
      const auditors = await res.json();
      if (auditors.length === 0) {
        list.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">No auditors found in the system.</span>';
        return;
      }
      list.innerHTML = auditors.map(a => `
        <label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:6px 0;">
          <input type="checkbox" name="auditor_ids" value="${a.id}" style="width:16px;height:16px;accent-color:var(--accent);" />
          <span style="font-size:14px;font-weight:500;color:var(--text-primary);">${window.AE.escapeHtml(a.name)}</span>
          <span style="font-size:12px;color:var(--text-muted);">@${window.AE.escapeHtml(a.username)}</span>
        </label>
      `).join('');
    } catch (e) {
      if (list) list.innerHTML = '<span style="color:var(--text-muted);font-size:13px;">Could not load auditors.</span>';
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    window.AE.initTopbar({ showBack: true, backHref: '/audit/index.html' });
    window.AE.initSidebar(PAGE_KEY);
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, PAGE_URL);

    const form = document.getElementById('form-new-engagement');
    if (form) {
      form.addEventListener('submit', handleSubmit);
    }
    
    await loadAuditors();
  });

  async function handleSubmit(e) {
    e.preventDefault();

    const client_name = document.getElementById('client_name')?.value?.trim();
    const financial_year = document.getElementById('financial_year')?.value?.trim();
    const period_start = document.getElementById('period_start')?.value;
    const period_end = document.getElementById('period_end')?.value;

    if (!client_name || !financial_year || !period_start || !period_end) {
      alert('All fields are required.');
      return;
    }

    // Basic date ordering validation
    if (new Date(period_start) > new Date(period_end)) {
      alert('Period Start date cannot be after Period End date.');
      return;
    }

    const submitBtn = document.getElementById('btn-create-engagement');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const res = await window.AE.apiFetch('/api/audit/engagements', {
        method: 'POST',
        body: JSON.stringify({ client_name, financial_year, period_start, period_end })
      });

      if (res.ok) {
        const data = await res.json();
        
        const checkedIds = Array.from(document.querySelectorAll('input[name="auditor_ids"]:checked'))
          .map(el => parseInt(el.value, 10));
        if (checkedIds.length > 0) {
          await window.AE.apiFetch(`/api/audit/engagements/${data.id}/auditors`, {
            method: 'POST',
            body: JSON.stringify({ user_ids: checkedIds })
          });
        }

        // Redirect to dashboard page
        window.location.href = `/audit/engagement.html?id=${data.id}`;
      } else {
        const errorData = await res.json().catch(() => ({}));
        alert(errorData.error || 'Failed to create engagement.');
        if (submitBtn) submitBtn.disabled = false;
      }
    } catch (err) {
      console.error(err);
      alert('Network error creating engagement.');
      if (submitBtn) submitBtn.disabled = false;
    }
  }
})();
