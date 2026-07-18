import type { Page } from '@playwright/test'

/** E2E helpers.
 *
 * Selectors target the actual UI (see `frontend/src/pages/RegisterPage.tsx`
 * and `LoginPage.tsx`). RegisterPage fields in DOM order:
 *   1. name  — `<input type="text">` (no placeholder)
 *   2. email — `<input type="email">` placeholder "user@example.com"
 *   3. password — `<input type="password">`
 *   4. carrier checkbox
 * Submit button copy: "Create account" (from `auth.register` in i18n).
 */

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
}

/** Register + auto-login (RegisterPage does both then navigates to /). */
export async function registerUser(page: Page, opts: RegisterOpts = {}) {
  const email = opts.email ?? uniqueEmail()
  const displayName = opts.displayName ?? `E2E ${email.slice(0, 8)}`

  await page.goto('/register')
  await page.waitForLoadState('domcontentloaded')

  // Fields — target by input type (name has no placeholder).
  await page.locator('input[type="text"]').first().fill(displayName)
  await page.locator('input[type="email"]').first().fill(email)
  await page.locator('input[type="password"]').first().fill(TEST_PASSWORD)

  if (opts.canCarry) {
    await page.locator('input[type="checkbox"]').first().check()
  }

  // Submit — button text: "Create account" (auth.register).
  await page
    .getByRole('button', { name: /create account|создать|зарегистрироваться|создати|zarejestruj|créer|crear/i })
    .first()
    .click()

  // Post-register RegisterPage navigates to "/". Wait for either landing
  // redirect or dashboard — just check we're off /register.
  await page
    .waitForURL((url) => !url.pathname.startsWith('/register'), { timeout: 15_000 })
    .catch(() => {})
  return { email, password: TEST_PASSWORD, displayName }
}

export async function login(page: Page, email: string, password = TEST_PASSWORD) {
  await page.goto('/login')
  await page.waitForLoadState('domcontentloaded')

  // LoginPage: email/phone field is a text input, password is password.
  await page.locator('input[type="text"], input[type="email"]').first().fill(email)
  await page.locator('input[type="password"]').first().fill(password)

  await page
    .getByRole('button', { name: /sign in|войти|увійти|zaloguj|connexion|iniciar/i })
    .first()
    .click()

  await page
    .waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 })
    .catch(() => {})
}
