/* =====================================================================
   theme.js — Dark/Light mode toggle
   Applies data-theme to <html>, persists to localStorage
   ===================================================================== */

(function () {
  const KEY = 'ae_theme';

  function getSystemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    updateToggleIcon(theme);
  }

  function updateToggleIcon(theme) {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    if (theme === 'dark') {
      btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"/>
          <line x1="12" y1="1" x2="12" y2="3"/>
          <line x1="12" y1="21" x2="12" y2="23"/>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
          <line x1="1" y1="12" x2="3" y2="12"/>
          <line x1="21" y1="12" x2="23" y2="12"/>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
        </svg>`;
      btn.setAttribute('aria-label', 'Switch to light mode');
      btn.title = 'Switch to light mode';
    } else {
      btn.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>`;
      btn.setAttribute('aria-label', 'Switch to dark mode');
      btn.title = 'Switch to dark mode';
    }
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || getSystemTheme();
    applyTheme(current === 'dark' ? 'light' : 'dark');
  }

  // Initialize on load
  const saved = localStorage.getItem(KEY);
  const initial = saved || getSystemTheme();
  document.documentElement.setAttribute('data-theme', initial);

  // Set up toggle after DOM is ready
  document.addEventListener('DOMContentLoaded', () => {
    updateToggleIcon(initial);
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.addEventListener('click', toggleTheme);
  });

  // Listen for system changes (if no user preference)
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem(KEY)) {
      applyTheme(e.matches ? 'dark' : 'light');
    }
  });

  // Expose globally
  window.AE = window.AE || {};
  window.AE.toggleTheme = toggleTheme;
  window.AE.applyTheme = applyTheme;
})();
