/* =====================================================================
   topbar.js — Topbar component initialization
   ===================================================================== */

(function () {
  window.AE = window.AE || {};

  /**
   * Renders the topbar HTML into #topbar-mount
   * @param {Object} opts
   * @param {boolean} opts.showBack - show back button
   * @param {string} opts.backHref - back button href (default: index.html)
   */
  async function initTopbar(opts = {}) {
    const mount = document.getElementById('topbar-mount');
    if (!mount) return;

    const showBack = opts.showBack !== false ? true : false;
    const backHref = opts.backHref || '/index.html';

    mount.innerHTML = `
      <header class="topbar" role="banner">
        <div class="topbar-left">
          <button class="btn-back ${showBack ? '' : 'hidden'}" onclick="history.length > 1 ? history.back() : location.href='${backHref}'" aria-label="Go back">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"/>
              <polyline points="12 19 5 12 12 5"/>
            </svg>
            Back
          </button>
        </div>

        <div class="topbar-center">
          <a href="/index.html" class="topbar-brand" aria-label="AuditEase home">
            Audit<span>Ease</span>
          </a>
        </div>

        <div class="topbar-right">
          <button class="topbar-btn" id="theme-toggle" aria-label="Toggle dark mode" title="Toggle dark mode">
            <!-- icon injected by theme.js -->
          </button>

          <a href="/timeline.html" class="topbar-btn" aria-label="Timeline" title="Timeline">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="2" x2="12" y2="6"/>
              <line x1="12" y1="18" x2="12" y2="22"/>
              <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/>
              <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/>
              <line x1="2" y1="12" x2="6" y2="12"/>
              <line x1="18" y1="12" x2="22" y2="12"/>
              <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/>
              <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/>
            </svg>
          </a>

          <a href="/reminders.html" class="topbar-btn" aria-label="Reminders" title="Reminders">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
          </a>

          <button class="account-btn" id="account-btn" aria-label="Account" aria-expanded="false">
            <!-- initials or icon injected by auth.js -->
          </button>
        </div>
      </header>

      <div class="account-panel hidden" id="account-panel" role="dialog" aria-label="Account panel">
        <!-- Logged In State Content (hidden by default) -->
        <div id="panel-logged-in" style="display: none;">
          <div class="account-panel-header">
            <h3>Account</h3>
            <p>Signed in to AuditEase</p>
          </div>
          <div class="account-panel-body">
            <div class="account-panel-user">
              <div class="account-panel-avatar" id="account-avatar">?</div>
              <div class="account-panel-user-info">
                <h4 id="account-name">User Name</h4>
                <p id="account-username">@username</p>
              </div>
            </div>
            <button class="btn btn-ghost w-full" id="logout-btn" style="justify-content:center;">
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
              Sign Out
            </button>
          </div>
        </div>

        <!-- Logged Out State Content (hidden by default) -->
        <div id="panel-logged-out" style="display: none;">
          <div class="account-panel-header">
            <h3>Sign In</h3>
            <p>Access AuditEase</p>
          </div>
          <div class="account-panel-body">
            <div class="form-group">
              <label for="login-username">Username</label>
              <input type="text" id="login-username" placeholder="Enter your username" autocomplete="username" />
            </div>
            <div class="form-group">
              <label for="login-password">Password</label>
              <input type="password" id="login-password" placeholder="Enter your password" autocomplete="current-password" />
            </div>
            <p class="login-error" id="login-error"></p>
            <button class="btn btn-primary" id="login-submit-btn" style="width:100%;justify-content:center;">
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
              Sign In
            </button>
          </div>
        </div>
      </div>
    `;

    // Re-initialize theme icon (theme.js may have run before DOM was injected)
    if (window.AE && window.AE.applyTheme) {
      const current = document.documentElement.getAttribute('data-theme') || 'light';
      // Fire the updateToggleIcon manually
      const saved = localStorage.getItem('ae_theme');
      const theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      // Trigger icon update by dispatching a synthetic event
      const themeBtn = document.getElementById('theme-toggle');
      if (themeBtn) {
        themeBtn.addEventListener('click', window.AE.toggleTheme);
        // Update icon immediately
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        themeBtn.innerHTML = isDark
          ? `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`
          : `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
      }
    }

    console.log('[AuditEase] Topbar injected into DOM');
    console.log('[AuditEase] #account-btn found:', !!document.getElementById('account-btn'));
    console.log('[AuditEase] #account-panel found:', !!document.getElementById('account-panel'));

    // Attach all listeners now that elements exist
    if (typeof attachAuthListeners === 'function') {
      attachAuthListeners();
    } else {
      console.error('[AuditEase] attachAuthListeners not defined — check script load order');
    }

    // Restore session if token exists
    const storedUser = localStorage.getItem('ae_user');
    const token = localStorage.getItem('ae_token');
    if (storedUser && token) {
      try {
        if (typeof window.updateAccountUI === 'function') {
          window.updateAccountUI(JSON.parse(storedUser));
        } else if (typeof window.AE?.updateAccountUI === 'function') {
          window.AE.updateAccountUI(JSON.parse(storedUser));
        }
      } catch(e) {
        localStorage.removeItem('ae_user');
        localStorage.removeItem('ae_token');
      }
    }

    // Return promise if initAuthUI exists (keep existing behaviour)
    if (typeof window.AE?.initAuthUI === 'function') {
      return window.AE.initAuthUI();
    }
  }

  window.AE.initTopbar = initTopbar;
  window.initTopbar = initTopbar;
})();
