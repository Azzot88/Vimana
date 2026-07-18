import type { Page } from '@playwright/test'

/** E2E test user helpers — deterministic random ids for parallel-safe reuse.
 *  All emails end with `@e2e.vimana.local` so the Celery cleanup task can
 *  prune them safely. */

export function uniqueEmail(prefix = 'e2e'): string {
  const rand = Math.random().toString(36).slice(2, 10)
  const ts = Date.now().toString(36)
  return `${prefix}-${ts}-${rand}@e2e.vimana.local`
}

export const TEST_PASSWORD = 'E2eSmoke!23'

export interface RegisterOpts {
  email?: string
  displayName?: string
  canCarry?: boolean
  activeMode?: 'sender' | 'carrier'
}

/** Register + auto-login. Returns the credentials so the caller can log back in. */
export async function registerUser(page: Page, opts: RegisterOpts = {}) {
  const email = opts.email ?? uniqueEmail()
  const displayName = opts.displayName ?? `E2E ${email.slice(0, 8)}`
  await page.goto('/register')
  await page.getByPlaceholder(/user@example\.com|email/i).fill(email)
  await page.getByPlaceholder(/password|••••/i).first().fill(TEST_PASSWORD)
  // Display name field — first text-input that isn't email/password.
  const nameField = page.getByPlaceholder(/name|имя|nom|nazwa/i).first()
  if (await nameField.count()) await nameField.fill(displayName)
  // Submit — "Sign up" / "Регистрация" / "Register" button.
  await page.getByRole('button', { name: /sign up|register|регистрация|создать/i }).first().click()
  await page.waitForURL(/\/dashboard/i, { timeout: 15_000 }).catch(() => {})
  return { email, password: TEST_PASSWORD, displayName }
}

export async function login(page: Page, email: string, password = TEST_PASSWORD) {
  await page.goto('/login')
  await page.getByPlaceholder(/user@example\.com|email/i).fill(email)
  await page.getByPlaceholder(/password|••••/i).first().fill(password)
  await page.getByRole('button', { name: /sign in|log in|войти/i }).first().click()
  await page.waitForURL(/\/dashboard/i, { timeout: 15_000 }).catch(() => {})
}
