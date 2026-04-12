import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        murmur: {
          bg: '#0a0e17',
          navy: '#0d1b2a',
          steel: '#1b2838',
          slate: '#2a3a4a',
          teal: '#2a8a7a',
          blue: '#4a9aca',
          'blue-soft': '#1a3a5c',
          amber: '#d4a574',
          copper: '#c47a4a',
          coral: '#e85d5d',
          red: '#ff4444',
        },
      },
      fontFamily: {
        sans: ['Inter', 'IBM Plex Sans', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config
