/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces & text map to CSS vars so light/dark switch happens in one place.
        bg: {
          primary: 'var(--bg-primary)',
          surface: 'var(--bg-surface)',
          raised: 'var(--bg-raised)',
        },
        border: {
          DEFAULT: 'var(--border)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          subtle: 'var(--accent-subtle)',
        },
        // Auditor-side accent tint (green) so the two identities read differently.
        auditor: {
          DEFAULT: 'var(--auditor-accent)',
          hover: 'var(--auditor-accent-hover)',
          subtle: 'var(--auditor-accent-subtle)',
        },
        status: {
          uploaded: 'var(--status-uploaded)',
          pending: 'var(--status-pending)',
          action: 'var(--status-action)',
          verified: 'var(--status-verified)',
          submitted: 'var(--status-submitted)',
          overdue: 'var(--status-overdue)',
          archived: 'var(--status-archived)',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        mono: ['IBM Plex Mono', 'Courier New', 'monospace'],
      },
      fontSize: {
        // Dense B2B scale anchored at 14px base.
        xs: ['11px', '16px'],
        sm: ['12px', '18px'],
        base: ['14px', '20px'],
        md: ['15px', '22px'],
        lg: ['18px', '26px'],
        xl: ['22px', '30px'],
      },
      borderRadius: {
        card: '6px',
        btn: '4px',
        input: '4px',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        modal: 'var(--shadow-modal)',
        dropdown: 'var(--shadow-dropdown)',
      },
      spacing: {
        topbar: '56px',
        sidebar: '220px',
        subnav: '40px',
      },
      transitionTimingFunction: {
        nav: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    },
  },
  plugins: [],
}
