import { expect, test, type CDPSession, type Page } from '@playwright/test'
import { registerUser } from '../helpers'

/**
 * T3.14 — passkeys against the real backend, with a virtual authenticator.
 *
 * This is the only place the WebAuthn exchange runs end to end. Unit tests
 * cover our rules (sign-count, lock-out guard) and the endpoint tests cover
 * ceremony state and ownership — but none of them produce a *valid* credential,
 * because that needs an authenticator. Chrome's virtual one, driven over CDP,
 * is that authenticator.
 *
 * **Requires `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN` to match the site under
 * test.** They default to `localhost`, so against prod they must be set to
 * `vimana.dealvault.club` / `https://vimana.dealvault.club` in `.env`. A
 * mismatch makes the browser abort before anything reaches the server — the
 * failure looks like "the button does nothing" with an empty server log, which
 * is why it is called out here rather than left to be rediscovered.
 */
async function attachAuthenticator(page: Page): Promise<CDPSession> {
  const client = await page.context().newCDPSession(page)
  await client.send('WebAuthn.enable')
  await client.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      // Discoverable credentials — without them usernameless login cannot work
      // at all, and that is the flow being tested.
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  })
  return client
}

test.describe('passkeys', () => {
  test('add a device, then sign in with it', async ({ page }) => {
    test.setTimeout(90_000)
    await attachAuthenticator(page)

    const user = await registerUser(page)

    await page.goto('/profile')
    await page.waitForLoadState('domcontentloaded')

    const [addResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/api/auth/passkey/register/verify') &&
          r.request().method() === 'POST',
        { timeout: 20_000 },
      ),
      page.getByTestId('passkey-add').click(),
    ])
    if (!addResp.ok()) {
      const body = await addResp.text().catch(() => '')
      throw new Error(
        `passkey register failed: HTTP ${addResp.status()} — ${body.slice(0, 300)}. ` +
          'If this is a 401 about origin or RP ID, check WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN.',
      )
    }

    await expect(page.getByTestId('passkey-list').locator('li')).toHaveCount(1)

    // Sign out completely — the point is that the passkey alone gets us back
    // in, with no password typed.
    await page.evaluate(() => localStorage.clear())
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    const [loginResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/api/auth/passkey/login/verify') &&
          r.request().method() === 'POST',
        { timeout: 20_000 },
      ),
      page.getByTestId('passkey-login').click(),
    ])
    expect(loginResp.ok(), await loginResp.text().catch(() => '')).toBeTruthy()

    await expect(page).toHaveURL(/\/(dashboard|verify-email)/, { timeout: 15_000 })

    // Same account, not a new one — the credential resolved to the user who
    // registered it.
    await page.goto('/profile')
    await expect(page.getByTestId('passkey-list').locator('li')).toHaveCount(1)
    expect(user.email).toBeTruthy()
  })

  test('the last way in cannot be removed', async ({ page }) => {
    /** A password account can drop its only passkey; the guard exists for the
     *  case where the passkey is the sole door. Here the account still has a
     *  password, so removal must succeed — this pins that the guard does not
     *  over-trigger, which would be just as broken as not triggering. */
    test.setTimeout(90_000)
    await attachAuthenticator(page)
    const { password } = await registerUser(page)

    await page.goto('/profile')
    await Promise.all([
      page.waitForResponse((r) =>
        r.url().includes('/api/auth/passkey/register/verify'),
      ),
      page.getByTestId('passkey-add').click(),
    ])
    await expect(page.getByTestId('passkey-list').locator('li')).toHaveCount(1)

    // T3.15 — unlinking now asks for a fresh confirmation first: dropping every
    // device but their own is how someone with a stolen session would lock the
    // owner out. This account has a password, so that is the proof offered.
    await page
      .getByTestId('passkey-list')
      .locator('li')
      .first()
      .getByRole('button')
      .click()
    const dialog = page.getByTestId('step-up-confirm')
    await expect(dialog).toBeVisible()
    await page.locator('input[type="password"]').last().fill(password)

    const [delResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/api/auth/passkey/') &&
          r.request().method() === 'DELETE',
      ),
      dialog.click(),
    ])
    expect(delResp.status()).toBe(204)
    await expect(page.getByTestId('passkey-list')).toHaveCount(0)
  })
})
