/* =====================================================================
   home.js — Home page logic
   ===================================================================== */

(function () {
  const PAGE_KEY = 'home';
  const PAGE_LABEL = 'Home';
  const PAGE_URL = '/index.html';

  const modules = [
    {
      id: 'audit',
      title: 'Audit',
      href: '/audit/index.html',
      pageKey: 'audit',
      pageLabel: 'Audit',
      desc: 'Manage and track audit engagements, working papers, and compliance documentation.',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`
    },
    {
      id: 'document-vault',
      title: 'Document Vault',
      href: '/documents/dashboard.html',
      pageKey: 'doc-dashboard',
      pageLabel: 'Document Dashboard',
      desc: 'Securely store, version, and track all your financial and compliance documents.',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>`
    },
    {
      id: 'secretarial',
      title: 'Secretarial',
      href: '/secretarial.html',
      pageKey: 'secretarial',
      pageLabel: 'Secretarial',
      desc: 'Handle corporate governance, board minutes, and statutory compliance filings.',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`
    },
    {
      id: 'roc',
      title: 'ROC',
      href: '/roc.html',
      pageKey: 'roc',
      pageLabel: 'ROC',
      desc: 'Registrar of Companies filings, annual returns, and regulatory submissions.',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><line x1="12" y1="12" x2="12" y2="16"/><line x1="10" y1="14" x2="14" y2="14"/></svg>`
    }
  ];

  document.addEventListener('DOMContentLoaded', async () => {
    // Init components
    window.AE.initTopbar({ showBack: false });
    window.AE.initSidebar(PAGE_KEY);

    // Track home visit
    window.AE.trackVisit(PAGE_KEY, PAGE_LABEL, PAGE_URL);

    // Render module cards
    renderCards();
  });

  function renderCards() {
    const grid = document.getElementById('home-grid');
    if (!grid) return;

    grid.innerHTML = modules.map(m => `
      <div class="module-card" id="card-${m.id}" data-href="${m.href}" data-page-key="${m.pageKey}" data-page-label="${m.pageLabel}" role="button" tabindex="0" aria-label="${m.title} module">
        <div class="module-card-content">
          <div class="module-card-icon">${m.icon}</div>
          <div class="module-card-title">${m.title}</div>
          <p class="module-card-desc">${m.desc}</p>
        </div>
      </div>
    `).join('');

    // Wire click & keyboard
    grid.querySelectorAll('.module-card').forEach(card => {
      const navigate = () => {
        const href = card.dataset.href;
        const key = card.dataset.pageKey;
        const label = card.dataset.pageLabel;
        window.AE.trackVisit(key, label, href);
        window.location.href = href;
      };
      card.addEventListener('click', navigate);
      card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(); }
      });
    });
  }
})();
