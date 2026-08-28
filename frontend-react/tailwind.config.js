/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['system-ui', 'Segoe UI', 'Arial', 'sans-serif'],
        mono: ['Consolas', 'Fira Code', 'monospace'],
      },
      colors: {
        cyber: {
          bg: '#070a12',
          surface: '#0d1322',
          panel: 'rgba(15, 23, 42, 0.75)',
          panelBorder: 'rgba(56, 189, 248, 0.2)',
          accent: '#6366f1',
          cyan: '#38bdf8',
          green: '#10b981',
          amber: '#f59e0b',
          red: '#ef4444',
          violet: '#8b5cf6',
          pink: '#ec4899',
        },
      },
      backgroundImage: {
        'cyber-gradient': 'linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%)',
        'approval-gradient': 'linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(239, 68, 68, 0.08) 100%)',
        'btn-gradient': 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
        'approve-btn': 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
      },
      boxShadow: {
        'glow-cyan': '0 0 16px -2px rgba(56, 189, 248, 0.5)',
        'glow-green': '0 0 16px -2px rgba(16, 185, 129, 0.5)',
        'glow-amber': '0 0 16px -2px rgba(245, 158, 11, 0.5)',
        'glow-red': '0 0 16px -2px rgba(239, 68, 68, 0.5)',
        'glow-violet': '0 0 16px -2px rgba(139, 92, 246, 0.5)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.45)',
      },
      backdropBlur: {
        glass: '16px',
      },
      animation: {
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 8px rgba(56, 189, 248, 0.3)' },
          '100%': { boxShadow: '0 0 20px rgba(56, 189, 248, 0.7)' },
        },
      },
    },
  },
  plugins: [],
};
