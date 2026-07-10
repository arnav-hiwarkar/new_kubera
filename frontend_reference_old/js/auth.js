/* =====================================================================
   auth.js — Client-side auth: JWT storage, login/logout UI
   ===================================================================== */

(function () {
  window.AE = window.AE || {};
  const TOKEN_KEY = 'ae_token';

  // ── Token helpers ──────────────────────────────────────────────────
  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  // ── API fetch with auth header ──────────────────────────────────────
  async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    if (options.body instanceof FormData) {
      delete headers['Content-Type']; // Let browser set multipart boundary
    }
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      clearToken();
      localStorage.removeItem('ae_user');
      currentUser = null;
      updateAccountUI(null);
      
      sessionStorage.setItem('ae_open_login', 'true');
      if (window.location.pathname !== '/' && window.location.pathname !== '/index.html') {
        window.location.href = '/index.html';
      } else {
        openAccountPanel();
      }
    }
    return res;
  }

  // ── Current user ────────────────────────────────────────────────────
  let currentUser = null;

  async function loadCurrentUser() {
    const token = getToken();
    if (!token) return null;
    try {
      const res = await apiFetch('/api/auth/me');
      if (res.ok) {
        const data = await res.json();
        currentUser = data.user;
        localStorage.setItem('ae_user', JSON.stringify(currentUser));
        return currentUser;
      }
    } catch (e) { /* silent */ }
    clearToken();
    localStorage.removeItem('ae_user');
    currentUser = null;
    return null;
  }

  function getCurrentUser() {
    return currentUser;
  }

  function getInitials(name) {
    if (!name) return '?';
    return name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase();
  }

  // ── Update account button ────────────────────────────────────────────
  function updateAccountBtn(user) {
    const btn = document.getElementById('account-btn');
    if (!btn) return;
    if (user) {
      btn.textContent = getInitials(user.name);
      btn.classList.add('logged-in');
      btn.title = user.name;
    } else {
      btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
      btn.classList.remove('logged-in');
      btn.title = 'Sign in';
    }
  }

  // ── Account Panel ────────────────────────────────────────────────────
  function renderAccountPanel(user) {
    const panel = document.getElementById('account-panel');
    if (!panel) return;

    const loggedInDiv = document.getElementById('panel-logged-in');
    const loggedOutDiv = document.getElementById('panel-logged-out');

    if (user) {
      // Update logged-in details
      const avatarEl = document.getElementById('account-avatar');
      const nameEl = document.getElementById('account-name');
      const usernameEl = document.getElementById('account-username');

      if (avatarEl) avatarEl.textContent = getInitials(user.name);
      if (nameEl) nameEl.textContent = user.name;
      if (usernameEl) usernameEl.textContent = `@${user.username}`;

      if (loggedInDiv) loggedInDiv.style.display = 'block';
      if (loggedOutDiv) loggedOutDiv.style.display = 'none';
    } else {
      // Reset login form fields
      const usernameInput = document.getElementById('login-username');
      const passwordInput = document.getElementById('login-password');
      const errorEl = document.getElementById('login-error');
      const loginBtn = document.getElementById('login-submit-btn');

      if (usernameInput) usernameInput.value = '';
      if (passwordInput) passwordInput.value = '';
      if (errorEl) errorEl.textContent = '';
      if (loginBtn) {
        loginBtn.disabled = false;
        loginBtn.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
          Sign In
        `;
      }

      if (loggedInDiv) loggedInDiv.style.display = 'none';
      if (loggedOutDiv) loggedOutDiv.style.display = 'block';
    }
  }

  async function handleLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errEl = document.getElementById('login-error');
    const btn = document.getElementById('login-submit-btn');

    if (!username || !password) {
      errEl.textContent = 'Please enter username and password';
      return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Signing in…';
    errEl.textContent = '';

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (res.ok) {
        setToken(data.token);
        currentUser = data.user;
        localStorage.setItem('ae_user', JSON.stringify(currentUser));
        updateAccountUI(currentUser);
      } else {
        errEl.textContent = data.error || 'Login failed';
        btn.disabled = false;
        btn.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
          Sign In
        `;
      }
    } catch (e) {
      errEl.textContent = 'Connection error. Please try again.';
      btn.disabled = false;
      btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
        Sign In
      `;
    }
  }

  async function handleSignOut() {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } catch (e) { /* silent */ }
    clearToken();
    localStorage.removeItem('ae_user');
    currentUser = null;
    updateAccountUI(null);
  }

  // ── Panel visibility ─────────────────────────────────────────────────
  function openAccountPanel() {
    const panel = document.getElementById('account-panel');
    if (!panel) {
      console.error('[AuditEase] openAccountPanel: #account-panel not found in DOM');
      return;
    }

    // Force show using inline style — overrides any CSS class hiding
    panel.style.setProperty('display', 'block', 'important');
    panel.style.setProperty('visibility', 'visible', 'important');
    panel.style.setProperty('opacity', '1', 'important');
    panel.style.setProperty('z-index', '9999', 'important');

    // Also remove any hiding classes just in case
    panel.classList.remove('hidden');
    panel.classList.add('visible');

    // Focus username input for immediate typing
    setTimeout(() => {
      const input = document.getElementById('login-username');
      if (input) input.focus();
    }, 50);

    console.log('[AuditEase] Account panel opened');
  }

  function closeAccountPanel() {
    const panel = document.getElementById('account-panel');
    if (!panel) return;
    panel.style.removeProperty('display');
    panel.style.removeProperty('visibility');
    panel.style.removeProperty('opacity');
    panel.classList.add('hidden');
    panel.classList.remove('visible');
  }

  function toggleAccountPanel() {
    const panel = document.getElementById('account-panel');
    if (panel) {
      if (panel.classList.contains('hidden') || panel.style.display === 'none') {
        openAccountPanel();
      } else {
        closeAccountPanel();
      }
    }
  }

  // ── Escape helper ────────────────────────────────────────────────────
  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ── Auth guard (for protected pages) ────────────────────────────────
  function showAuthGuard() {
    // disabled — using topbar login instead
  }

  // ── updateAccountUI ──────────────────────────────────────────────────
  function updateAccountUI(user) {
    updateAccountBtn(user);
    closeAccountPanel();
    renderAccountPanel(user);

    // After login, reload the current page's data
    if (typeof window.initDashboard === 'function') window.initDashboard();
    if (typeof window.initVault === 'function') window.initVault();
    if (typeof window.initArchives === 'function') window.initArchives();

    if (typeof window.onAuthChange === 'function') {
      window.onAuthChange(user);
    }
  }

  // ── attachAuthListeners ──────────────────────────────────────────────
  function attachAuthListeners() {
    console.log('[AuditEase] attachAuthListeners called');

    const accountBtn = document.getElementById('account-btn');
    const loginBtn = document.getElementById('login-submit-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const passwordInput = document.getElementById('login-password');

    if (!accountBtn) console.error('[AuditEase] #account-btn not found');
    if (!loginBtn) console.error('[AuditEase] #login-submit-btn not found');
    if (!logoutBtn) console.error('[AuditEase] #logout-btn not found');

    accountBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleAccountPanel();
    });

    loginBtn?.addEventListener('click', handleLogin);

    passwordInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') handleLogin();
    });

    logoutBtn?.addEventListener('click', handleSignOut);

    // Close panel when clicking outside
    document.addEventListener('click', (e) => {
      const panel = document.getElementById('account-panel');
      const accountBtn = document.getElementById('account-btn');
      if (panel && !panel.contains(e.target) && !accountBtn?.contains(e.target)) {
        closeAccountPanel();
      }
    });

    console.log('[AuditEase] All auth listeners attached successfully');
  }

  window.attachAuthListeners = attachAuthListeners;

  // ── initAuthUI — called by topbar.js AFTER topbar HTML is injected ──────
  async function initAuthUI() {
    const user = await loadCurrentUser();
    updateAccountUI(user, true);
    if (!user && sessionStorage.getItem('ae_open_login') === 'true') {
      sessionStorage.removeItem('ae_open_login');
      openAccountPanel();
    }
  }

  // ── Exports ───────────────────────────────────────────────────────────
  window.AE.getToken = getToken;
  window.AE.apiFetch = apiFetch;
  window.AE.getCurrentUser = getCurrentUser;
  window.AE.loadCurrentUser = loadCurrentUser;
  window.AE.escapeHtml = escapeHtml;
  window.AE.updateAccountBtn = updateAccountBtn;
  window.AE.renderAccountPanel = renderAccountPanel;
  window.AE.initAuthUI = initAuthUI;  // Called by topbar.js after HTML injection
  window.AE.updateAccountUI = updateAccountUI;
  window.AE.openAccountPanel = openAccountPanel;
  window.AE.closeAccountPanel = closeAccountPanel;
  window.AE.showAuthGuard = showAuthGuard;
  window.openAccountPanel = openAccountPanel;
  window.updateAccountUI = updateAccountUI;
})();
