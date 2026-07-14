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
          inset: 'var(--bg-inset)',
        },
        border: {
          DEFAULT: 'var(--border)',
          strong: 'var(--border-strong)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        // Company identity — emerald "prosperity" primary.
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          active: 'var(--accent-active)',
          subtle: 'var(--accent-subtle)',
          contrast: 'var(--accent-contrast)',
        },
        // Warm gold micro-accent (used sparingly for highlights/premium touches).
        gold: {
          DEFAULT: 'var(--gold)',
          soft: 'var(--gold-soft)',
          subtle: 'var(--gold-subtle)',
        },
        // Auditor-side accent (cool slate/blue) so the two identities read differently.
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
        // Dense B2B scale anchored at 14px base, plus display sizes for headings.
        xs: ['11px', '16px'],
        sm: ['12px', '18px'],
        base: ['14px', '20px'],
        md: ['15px', '22px'],
        lg: ['18px', '26px'],
        xl: ['22px', '30px'],
        '2xl': ['28px', '34px'],
        '3xl': ['36px', '42px'],
        '4xl': ['48px', '52px'],
      },
      borderRadius: {
        card: '14px',
        btn: '10px',
        input: '10px',
        pill: '999px',
        lg: '12px',
        xl: '18px',
        '2xl': '22px',
      },
      boxShadow: {
        xs: 'var(--shadow-xs)',
        card: 'var(--shadow-card)',
        raised: 'var(--shadow-raised)',
        modal: 'var(--shadow-modal)',
        dropdown: 'var(--shadow-dropdown)',
        glow: 'var(--shadow-glow)',
      },
      spacing: {
        topbar: '60px',
        sidebar: '244px',
        'sidebar-collapsed': '68px',
        subnav: '44px',
      },
      transitionTimingFunction: {
        nav: 'cubic-bezier(0.4, 0, 0.2, 1)',
        spring: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      backgroundImage: {
        'accent-gradient': 'linear-gradient(135deg, var(--accent) 0%, var(--accent-active) 100%)',
      },
    },
  },
  plugins: [],
}
