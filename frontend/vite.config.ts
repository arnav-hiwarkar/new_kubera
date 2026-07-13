<<<<<<< HEAD
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
=======
/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
>>>>>>> new_frontend
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
<<<<<<< HEAD
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/__tests__/setup.ts'],
    globals: true,
  }
=======
  server: {
    port: 5173,
    proxy: {
      // Dev-only: proxy API calls to the FastAPI backend to avoid CORS.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
  },
>>>>>>> new_frontend
})
