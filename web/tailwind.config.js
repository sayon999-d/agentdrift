/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#08080a',
        peony: '#ff2a4b',
        signal: '#00f0ff',
        phosphor: '#4a5568',
      },
      fontFamily: {
        mono: ['DM Mono', 'monospace'],
        display: ['Space Grotesk', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
