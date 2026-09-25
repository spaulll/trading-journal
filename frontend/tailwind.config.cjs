/** @type {import('tailwindcss').Config} */
module.exports = {
	darkMode: 'class',
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
				mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace']
			},
			boxShadow: {
				card: '0 1px 2px rgb(2 6 23 / 0.06), 0 4px 16px -4px rgb(2 6 23 / 0.08)',
				pop: '0 8px 32px -8px rgb(2 6 23 / 0.25), 0 2px 8px rgb(2 6 23 / 0.12)',
				lift: '0 6px 20px -6px rgb(16 185 129 / 0.25), 0 2px 8px rgb(2 6 23 / 0.12)'
			},
			colors: {
				surface: {
					50: '#f8fafc',
					100: '#f1f5f9',
					700: '#1a1d24',
					800: '#12141a',
					850: '#14161b',
					900: '#0b0c10',
					950: '#060709'
				},
				accent: {
					win: '#10b981',
					winDim: '#133e35',
					loss: '#ef4444',
					lossDim: '#451e24',
					be: '#64748b'
				}
			}
		}
	},
	plugins: [require('@tailwindcss/forms')]
};
