/* =====================================================================
   sidebar.js — Sidebar component: Quick Access, sections
   ===================================================================== */

(function () {
  window.AE = window.AE || {};

  async function initSidebar(currentPageKey) {
    const mount = document.getElementById('sidebar-mount');
    if (!mount) return;

    mount.innerHTML = `
      <nav class="sidebar" role="navigation" aria-label="Sidebar">

        <!-- Section 1: Quick Access -->
        <div class="sidebar-section">
          <div class="sidebar-label">Quick Access</div>
          <div id="sidebar-qa-list">
            ${[1,2,3,4,5].map(() => `<div class="sidebar-qa-placeholder">—</div>`).join('')}
          </div>
        </div>

        <!-- Section 2: Timeline -->
        <div class="sidebar-section">
          <div class="sidebar-label">Timeline</div>
          <div class="sidebar-section-reserve"></div>
        </div>

        <!-- Section 3: Reminders -->
        <div class="sidebar-section">
          <div class="sidebar-label">Reminders</div>
          <div class="sidebar-section-reserve"></div>
        </div>

        <!-- Section 4: Learn More -->
        <div class="sidebar-section">
          <a href="/learn-more.html" class="sidebar-learn-more" id="sidebar-learn-more">
            Learn More
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </a>
        </div>
      </nav>
    `;

    // Load quick access data if user is logged in
    await loadQuickAccess(currentPageKey);
  }

  async function loadQuickAccess(currentPageKey) {
    const list = document.getElementById('sidebar-qa-list');
    if (!list) return;

    const token = window.AE.getToken ? window.AE.getToken() : null;
    if (!token) {
      list.innerHTML = `<div class="sidebar-qa-placeholder" style="font-style:italic;font-size:11px;color:var(--text-muted);">Sign in to see quick access</div>`;
      return;
    }

    try {
      const res = await window.AE.apiFetch('/api/visits/top');
      if (!res.ok) throw new Error();
      const visits = await res.json();

      const filtered = visits.filter(v => v.page_key !== currentPageKey);
      if (filtered.length === 0) {
        list.innerHTML = `<div class="sidebar-qa-placeholder" style="font-size:11px;color:var(--text-muted);">No recent pages yet</div>`;
        return;
      }

      list.innerHTML = filtered.map(v => `
        <a href="${window.AE.escapeHtml(v.page_url)}" class="sidebar-qa-item" data-page-key="${window.AE.escapeHtml(v.page_key)}">
          <span class="qa-label">${window.AE.escapeHtml(v.page_label)}</span>
          <span class="sidebar-qa-badge">${v.visit_count}</span>
        </a>
      `).join('');
    } catch (e) {
      list.innerHTML = `<div class="sidebar-qa-placeholder" style="font-size:11px;color:var(--text-muted);">—</div>`;
    }
  }

  // Track a page visit
  async function trackVisit(pageKey, pageLabel, pageUrl) {
    const token = window.AE.getToken ? window.AE.getToken() : null;
    if (!token) return;
    try {
      await window.AE.apiFetch('/api/visits', {
        method: 'POST',
        body: JSON.stringify({ page_key: pageKey, page_label: pageLabel, page_url: pageUrl })
      });
    } catch (e) { /* silent */ }
  }

  window.AE.initSidebar = initSidebar;
  window.AE.trackVisit = trackVisit;
})();
