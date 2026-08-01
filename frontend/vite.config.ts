/// <reference types="vitest" />
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    allowedHosts: ['vimana.dealvault.club', '.dealvault.club'],
  },
  build: {
    // Split heavy vendors so the main bundle stays under 500 kB and the browser
    // can cache the (rarely-changing) libraries separately from our code.
    rollupOptions: {
      // T3.24 — two entries. `reader.html` is a standalone page for opening a
      // `.dvlt`; it is not a route, because a route would need the server to
      // serve it and this page exists for the case where the server is exactly
      // what you do not have.
      input: {
        main: resolve(__dirname, 'index.html'),
        reader: resolve(__dirname, 'reader.html'),
      },
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-i18n': ['i18next', 'react-i18next'],
          'vendor-phone': ['libphonenumber-js'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Scope vitest to `src/`. The default glob also swept `e2e/specs/*.spec.ts`,
    // which belong to Playwright — a separate npm package with its own runner.
    // Vitest collected them, called Playwright's `test()` outside a Playwright
    // run, and reported eight failed suites that were never vitest's to run.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
