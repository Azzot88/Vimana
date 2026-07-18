import { defineConfig, devices } from '@playwright/test'

/**
 * Vimana smoke suite. Default target = prod
 * (https://vimana.dealvault.club). Override with SMOKE_BASE_URL env.
 *
 * All test users are registered with `+e2e-<random>@e2e.vimana.local` — TLD
 * is unreachable, so the address never sends a real email. Backend Celery
 * task `cleanup_e2e_users` prunes them older than 24 h.
 */
export default defineConfig({
  testDir: './specs',
  fullyParallel: false,          // sequential — shared prod DB, no races please
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? 'https://vimana.dealvault.club',
    trace: 'on',                 // always record trace — opened via show-trace
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
