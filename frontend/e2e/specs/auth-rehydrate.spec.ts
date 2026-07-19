import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/** Multi-context #2 — regression test for T_UX.3 pt.1. After registration
 *  (Zustand fully populated), open a **second page** in the same context
 *  and hard-nav directly to a protected route. `<AuthBootstrap>` must
 *  rehydrate from localStorage.token → GET /api/auth/me → set user, and the
 *  page must render without redirecting to /login.
 *
 *  Reproduces the exact race that broke `/join/deal/:token` before pt.1. */
test('auth rehydrate: hard-nav to protected route in fresh page keeps session', async ({
  browser,
}) => {
  test.setTimeout(60_000)

  const context = await browser.newContext()
  const registerPage = await context.newPage()

  try {
    const user = await registerUser(registerPage, {
      email: uniqueEmail('e2e-rh'),
      displayName: 'E2E Rehydrate',
    })

    // Confirm localStorage.token is set (Zustand persist).
    const token = await registerPage.evaluate(() => localStorage.getItem('token'))
    expect(token, 'no token in localStorage after register').toBeTruthy()

    // Close registration page — force a completely fresh page load path
    // (no in-memory Zustand state, no window carryover). Shared cookies +
    // localStorage remain because it's the same context.
    await registerPage.close()

    const freshPage = await context.newPage()

    // Direct hard-nav to /profile — the classic "click a link in email"
    // pattern. Must NOT redirect to /login.
    const [meResp] = await Promise.all([
      freshPage.waitForResponse(
        (r) => r.url().includes('/api/auth/me') && r.request().method() === 'GET',
        { timeout: 15_000 },
      ),
      freshPage.goto('/profile'),
    ])
    expect(meResp.ok(), `rehydrate GET /auth/me failed HTTP ${meResp.status()}`).toBe(true)

    // URL must stay on /profile, not bounce to /login.
    await freshPage.waitForLoadState('domcontentloaded')
    await expect(freshPage).toHaveURL(/\/profile/)
    await expect(freshPage).not.toHaveURL(/\/login/)

    const bodyText = await freshPage.locator('body').innerText()
    expect(bodyText, 'profile body should include the user email').toContain(user.email)

    console.log(`Rehydrate ok — user=${user.email}, token-length=${token?.length}`)
  } finally {
    await context.close()
  }
})
