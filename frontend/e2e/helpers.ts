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


/**
 * T_TEST.8 (2026-08-22) — sign in as the fixed e2e account.
 *
 * `registerUser` below drives the registration form, and that form stopped
 * existing on 2026-08-10: T3.28 reduced sign-in and sign-up to one field plus a
 * code, and `/register` now redirects to `/login`. A test cannot read the code,
 * so it cannot create an account at all — owner's decision 2026-08-22 is to use
 * a small number of long-lived accounts instead.
 *
 * **Authentication happens through the API, not the form.** What broke was a
 * test driving a UI it was not testing; setup should not depend on markup that
 * belongs to somebody else's feature. The login *screen* still gets covered —
 * by the specs that are actually about signing in.
 *
 * Requires `E2E_USER` / `E2E_PASSWORD`. Missing values fail loudly rather than
 * timing out on a locator fifteen seconds later, which is how the last breakage
 * managed to look like six different problems.
 */
export interface SignInOpts {
  /** Set `active_mode` after signing in. The panel and the nav differ by mode,
   *  so a spec that means "as a carrier" has to say so. */
  mode?: 'carrier' | 'sender'
}

export async function signInFixed(page: Page, opts: SignInOpts = {}) {
  const login = process.env.E2E_USER
  const password = process.env.E2E_PASSWORD
  if (!login || !password) {
    throw new Error(
      'E2E_USER / E2E_PASSWORD are not set. The suite signs in as a long-lived ' +
        'account (owner\'s decision 2026-08-22): registration through the UI is ' +
        'code-based since T3.28 and cannot be automated.',
    )
  }

  const res = await page.request.post('/api/auth/login', {
    data: { login, password },
  })
  if (!res.ok()) {
    throw new Error(
      `login failed for ${login}: ${res.status()} ${await res.text()}`,
    )
  }
  const { access_token: token } = (await res.json()) as { access_token: string }

  // Origin first: `localStorage` belongs to one, and setting it before any
  // navigation writes it into `about:blank`.
  await page.goto('/')
  await page.evaluate((t) => localStorage.setItem('token', t), token)

  if (opts.mode) {
    const patch = await page.request.patch('/api/auth/me', {
      data: { active_mode: opts.mode },
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!patch.ok()) {
      throw new Error(`could not switch to ${opts.mode}: ${patch.status()}`)
    }
  }

  return { login, token }
}

/** @deprecated Broken since T3.28 (2026-08-10): `/register` redirects to
 *  `/login` and the three-field form is gone. Left in place because nine specs
 *  still call it and converting them is its own task — see T_TEST.8. New specs
 *  use `signInFixed`. */
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

  // RegisterPage chains 3 XHRs: POST /register → POST /login → GET /me →
  // navigate('/'). Wait for all three, throw loud with URL+status if any fail.
  // Otherwise a rate-limited login step just leaves the browser on /register
  // with an amber error banner and the URL check below times out mysteriously.
  const authResponses: Array<{ url: string; status: number }> = []
  page.on('response', (r) => {
    const u = r.url()
    if (u.includes('/api/auth/register') || u.includes('/api/auth/login') || u.includes('/api/auth/me')) {
      authResponses.push({ url: u, status: r.status() })
    }
  })

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

  try {
    await expect(page).not.toHaveURL(/\/register$/, { timeout: 8_000 })
  } catch {
    const trail = authResponses.map((r) => `${r.status} ${r.url.replace(/^https?:\/\/[^/]+/, '')}`).join(' | ')
    const visible = (await page.locator('body').innerText().catch(() => '')).slice(0, 200)
    throw new Error(
      `Register chain stuck on /register. Auth XHR trail: [${trail}]. Visible: ${visible}`,
    )
  }
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
