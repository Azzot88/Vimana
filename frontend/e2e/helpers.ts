import { expect, type Page } from '@playwright/test'

/** E2E helpers. Faster + louder: wait for real XHRs, fail with detail if
 *  register/login didn't actually succeed on the backend. */

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

/** Register + auto-login. Fails loud if the backend didn't 201. */
export async function registerUser(page: Page, opts: RegisterOpts = {}) {
  const email = opts.email ?? uniqueEmail()
  const displayName = opts.displayName ?? `E2E ${email.slice(0, 8)}`

  await page.goto('/register')
  await page.waitForLoadState('domcontentloaded')

  await page.locator('input[type="text"]').first().fill(displayName)
  await page.locator('input[type="email"]').first().fill(email)
  await page.locator('input[type="password"]').first().fill(TEST_PASSWORD)

  if (opts.canCarry) {
    await page.locator('input[type="checkbox"]').first().check()
  }

  // Watch the real /api/auth/register XHR — throw with body detail if not ok.
  const [regResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/auth/register') && r.request().method() === 'POST',
      { timeout: 10_000 },
    ),
    page
      .getByRole('button', { name: /create account|создать|зарегистрироваться|создати|zarejestruj|créer|crear/i })
      .first()
      .click(),
  ])
  if (!regResp.ok()) {
    const body = await regResp.text().catch(() => '')
    throw new Error(`Register failed: HTTP ${regResp.status()} — ${body.slice(0, 200)}`)
  }

  await expect(page).not.toHaveURL(/\/register$/, { timeout: 8_000 })
  return { email, password: TEST_PASSWORD, displayName }
}

export async function login(page: Page, email: string, password = TEST_PASSWORD) {
  await page.goto('/login')
  await page.waitForLoadState('domcontentloaded')
  await page.locator('input[type="text"], input[type="email"]').first().fill(email)
  await page.locator('input[type="password"]').first().fill(password)
  const [loginResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/auth/login') && r.request().method() === 'POST',
      { timeout: 10_000 },
    ),
    page
      .getByRole('button', { name: /sign in|войти|увійти|zaloguj|connexion|iniciar/i })
      .first()
      .click(),
  ])
  if (!loginResp.ok()) {
    const body = await loginResp.text().catch(() => '')
    throw new Error(`Login failed: HTTP ${loginResp.status()} — ${body.slice(0, 200)}`)
  }
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 8_000 })
}
