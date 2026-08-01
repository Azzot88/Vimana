/// <reference types="vitest" />
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

/**
 * Two builds, one config.
 *
 * `npm run build` runs the app build and then the reader build (`--mode
 * reader`). They are separate because they want opposite things: the app wants
 * code splitting and cacheable vendor chunks, the reader wants **one file** —
 * it is meant to be saved to disk and opened when there is no server to fetch
 * an `/assets/*.js` from (T3.24). Applying `viteSingleFile` to both would
 * inline the whole SPA into one HTML and throw away every caching property the
 * app build has.
 *
 * The reader build must not empty `dist/`: it runs second, and the app's output
 * is already there.
 */
export default defineConfig(({ mode }) => {
  const isReader = mode === 'reader'

  return {
    plugins: isReader ? [viteSingleFile()] : [react()],
    server: {
      host: true,
      allowedHosts: ['vimana.dealvault.club', '.dealvault.club'],
    },
    build: isReader
      ? {
          emptyOutDir: false,
          rollupOptions: {
            input: resolve(__dirname, 'reader.html'),
          },
        }
      : {
          // Split heavy vendors so the main bundle stays under 500 kB and the
          // browser can cache the (rarely-changing) libraries separately from
          // our code.
          rollupOptions: {
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
  }
})
