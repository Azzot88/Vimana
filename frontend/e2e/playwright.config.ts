import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

/**
 * Vimana smoke suite. Default target = prod
 * (https://vimana.dealvault.club). Override with SMOKE_BASE_URL env.
 *
 * **Two kinds of account, and the difference matters.**
 *
 * Specs that still call `registerUser` mint `e2e-<random>@e2e.vimana.local`;
 * the TLD is unreachable, so nothing is ever delivered, and Celery's
 * `cleanup_e2e_users` prunes them after 24 h. That path has been broken since
 * T3.28 made registration code-based — see T_TEST.8.
 *
 * Specs that call `signInFixed` use one long-lived account on a **real**
 * mailbox, because the registration code has to be readable by a person once.
 * A real address also puts it outside the sweep above, which is what a
 * permanent account needs.
 */

/** Credentials belong in an untracked file, not in a shell history and not in
 *  this repo. `.env.local` is git-ignored (`.env.example` next to it is not, and
 *  carries the keys without the values); this reads it without adding a
 *  dependency for eight lines of parsing. Real environment variables win, so
 *  CI can set them without a file. */
function loadLocalEnv() {
  const path = fileURLToPath(new URL('.env.local', import.meta.url))
  if (!existsSync(path)) return
  for (const line of readFileSync(path, 'utf-8').split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq < 1) continue
    const key = trimmed.slice(0, eq).trim()
    if (process.env[key] !== undefined) continue
    process.env[key] = trimmed.slice(eq + 1).trim().replace(/^['"]|['"]$/g, '')
  }
}

loadLocalEnv()
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
    // Slow-mo lives in launchOptions (Playwright removed the CLI flag in
    // 1.49). Override with `SLOW_MO=1000 npm run headed` when you want to
    // watch even more slowly, or `SLOW_MO=0` for full speed.
    launchOptions: {
      slowMo: Number(process.env.SLOW_MO ?? 300),
    },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
