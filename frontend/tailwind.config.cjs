/** @type {import('tailwindcss').Config} */
module.exports = {
	darkMode: 'class',
	content: ['./src/**/*.{html,js,svelte,ts}'],
	theme: {
		extend: {
			fontFamily: {
				sans: ['Inter', 'sans-serif'],
				mono: ['JetBrains Mono', 'monospace']
			},
			colors: {
				surface: {
					50: '#f8fafc',
					100: '#f1f5f9',
					800: '#12141a',
					900: '#0b0c10',
					950: '#060709'
				},
				accent: {
					win: '#10b981',
					loss: '#ef4444',
					be: '#64748b'
				}
			}
		}
	},
	plugins: [require('@tailwindcss/forms')]
};
