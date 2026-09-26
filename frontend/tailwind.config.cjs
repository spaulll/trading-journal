/**
 * Onyx & Brass — design tokens.
 * Theme-aware surfaces/semantic colors resolve through CSS variables set in
 * app.css (`:root` light, `.dark` inverted), so every utility stays correct in
 * both themes without `dark:` duplication.
 *
 * @type {import('tailwindcss').Config}
 */
module.exports = {
	darkMode: 'class',
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			/* Every integer percentage so tinted utilities (`bg-win/12`) always resolve. */
			opacity: Object.fromEntries(Array.from({ length: 101 }, (_, i) => [i, String(i / 100)])),
			fontFamily: {
				sans: ['Geist', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
				mono: ['Geist Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
				display: ['Instrument Serif', 'Iowan Old Style', 'Georgia', 'serif']
			},
			colors: {
				/* Surfaces */
				base: 'rgb(var(--c-bg) / <alpha-value>)',
				panel: 'rgb(var(--c-panel) / <alpha-value>)',
				raised: 'rgb(var(--c-raised) / <alpha-value>)',
				/* Hairlines (fixed per-theme alpha) */
				line: 'rgb(var(--c-line))',
				edge: 'rgb(var(--c-edge))',
				/* Type */
				fg: 'rgb(var(--c-fg) / <alpha-value>)',
				mut: 'rgb(var(--c-mut) / <alpha-value>)',
				dim: 'rgb(var(--c-dim) / <alpha-value>)',
				/* Theme-aware brand accent (text/icons on any surface) */
				accent: 'rgb(var(--c-accent) / <alpha-value>)',
				/* Brand — brass */
				brass: {
					50: '#FBF5E7',
					100: '#F7EACB',
					200: '#EFDBA8',
					300: '#E7CB86',
					400: '#DCB964',
					500: '#C9A149',
					600: '#A87F31',
					700: '#866224',
					800: '#6B4E1F',
					900: '#523C1B',
					ink: 'rgb(var(--c-brass-ink) / <alpha-value>)'
				},
				/* Semantic P&L */
				win: 'rgb(var(--c-win) / <alpha-value>)',
				loss: 'rgb(var(--c-loss) / <alpha-value>)',
				flat: 'rgb(var(--c-flat) / <alpha-value>)'
			},
			boxShadow: {
				card: '0 1px 2px rgb(0 0 0 / 0.20), 0 12px 32px -24px rgb(0 0 0 / 0.65)',
				lift: '0 2px 6px rgb(0 0 0 / 0.28), 0 24px 48px -28px rgb(0 0 0 / 0.85)',
				pop: '0 4px 12px rgb(0 0 0 / 0.35), 0 40px 80px -40px rgb(0 0 0 / 0.95)',
				brass: '0 1px 0 rgb(255 255 255 / 0.22) inset, 0 8px 22px -12px rgb(201 161 73 / 0.75)',
				hair: 'inset 0 1px 0 rgb(255 255 255 / 0.05)',
				glow: '0 0 0 1px rgb(201 161 73 / 0.25), 0 12px 40px -18px rgb(201 161 73 / 0.55)'
			},
			borderRadius: {
				'4xl': '2rem'
			},
			transitionTimingFunction: {
				spring: 'cubic-bezier(0.22, 1, 0.36, 1)',
				soft: 'cubic-bezier(0.4, 0, 0.2, 1)'
			},
			keyframes: {
				rise: {
					'0%': { opacity: '0', transform: 'translateY(14px)' },
					'100%': { opacity: '1', transform: 'none' }
				},
				fade: {
					'0%': { opacity: '0' },
					'100%': { opacity: '1' }
				},
				draw: {
					to: { 'stroke-dashoffset': '0' }
				},
				sheen: {
					'0%': { transform: 'translateX(-120%)' },
					'100%': { transform: 'translateX(220%)' }
				},
				breathe: {
					'0%, 100%': { opacity: '0.55', transform: 'translate3d(0,0,0) scale(1)' },
					'50%': { opacity: '0.9', transform: 'translate3d(2%, 3%, 0) scale(1.06)' }
				},
				'shimmer-x': {
					'0%': { backgroundPosition: '-200% 0' },
					'100%': { backgroundPosition: '200% 0' }
				}
			},
			animation: {
				rise: 'rise 0.6s cubic-bezier(0.22, 1, 0.36, 1) both',
				fade: 'fade 0.5s cubic-bezier(0.22, 1, 0.36, 1) both',
				sheen: 'sheen 1.1s cubic-bezier(0.4, 0, 0.2, 1)',
				breathe: 'breathe 18s ease-in-out infinite',
				'shimmer-x': 'shimmer-x 1.6s linear infinite'
			}
		}
	},
	plugins: [require('@tailwindcss/forms')]
};
