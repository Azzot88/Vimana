import { expect, test, type Page } from '@playwright/test'

/** Stands where `registerUser` used to, and refuses.
 *
 *  Signing in as the shared account here would be worse than failing: the first
 *  run would pass and irreversibly retire that account's service key, taking
 *  every other spec with it. So the placeholder throws instead — unskipping is
 *  only meaningful together with one of the two fixes in the note below. */
async function needsAnAccountThatNeverEstablished(_page: Page): Promise<never> {
  throw new Error(
    'identity: establish needs an account that has never established, and the ' +
      'suite can no longer create one (T3.28). Read the note at the top of ' +
      'this file before unskipping — the shared account is not a substitute.',
  )
}

/**
 * T3.12 — taking ownership of your identity, in a real browser.
 *
 * This is the only place the client-side crypto actually runs against the real
 * backend: `@noble/curves` generates the key and signs the challenge, and the
 * server verifies that signature with `coincurve`. Unit tests pin the canonical
 * serialization on both sides (`src/test/identity.test.ts` +
 * `backend/tests/test_identity_proof_contract.py`), but only this spec proves
 * the two BIP-340 implementations actually agree end to end.
 *
 * **A fresh account every run, always.** Establishing is irreversible: the
 * second attempt on the same account answers 409. A spec pinned to a fixed
 * login would pass once and then fail forever, and the failure would look like
 * a regression rather than a test defect.
 *
 * The NIP-07 branch is not covered here — a real extension needs a persistent
 * context (see T_TEST.3 notes). The browser-generated branch is the default
 * path and the one carrying the crypto risk.
 *
 * ── Why this is skipped (T_TEST.12, 2026-08-23) ─────────────────────────────
 *
 * The paragraph above was written as a note about test hygiene. It is now the
 * blocker. Every other spec moved from `registerUser` to a long-lived account
 * when T3.28 made sign-up code-based and unautomatable; this one cannot follow,
 * because the thing it tests can only happen once per account. A fixed login
 * would go green on its first run and red on every run after, permanently.
 *
 * Skipped rather than deleted or quietly rewritten to assert less. This is the
 * only place the two BIP-340 implementations — `@noble/curves` in the browser,
 * `coincurve` on the server — are proved to agree end to end, and a version
 * that dropped that would keep the name while testing nothing.
 *
 * Unskipping needs **one** of:
 *   - a way for a test to create an account (a test-only path past the mailed
 *     code — an owner's decision, it trades safety for testability), or
 *   - a way to return an account to `service` custody, which today is not a
 *     thing the product can do to itself and probably should not be.
 *
 * Until then the coverage gap is real and stated: the serialization contract is
 * still pinned by unit tests on both sides (`src/test/identity.test.ts`,
 * `backend/tests/test_identity_proof_contract.py`); what is unproved is that
 * the two libraries agree at runtime. See TASKS `T_TEST.12`.
 */
test.describe.skip('identity: establish', () => {
  test('generates a key in the browser and the backend accepts it', async ({
    page,
  }) => {
    await needsAnAccountThatNeverEstablished(page)

    await page.goto('/profile/keys')
    await page.waitForLoadState('domcontentloaded')

    const state = page.getByTestId('identity-state')
    await expect(state).toHaveAttribute('data-state', 'service')

    await page.getByTestId('identity-start').click()
    await page.getByTestId('identity-generate').click()

    // The key is on screen and nothing has been sent yet. Confirming that it
    // was saved is mandatory — after the transition it cannot be recovered.
    const confirm = page.getByTestId('identity-confirm')
    await expect(confirm).toBeDisabled()

    await page.getByTestId('identity-saved').check()
    await expect(confirm).toBeEnabled()

    const [establishResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/api/me/identity/establish') &&
          r.request().method() === 'POST',
        { timeout: 15_000 },
      ),
      confirm.click(),
    ])

    if (!establishResp.ok()) {
      const body = await establishResp.text().catch(() => '')
      throw new Error(
        `establish failed: HTTP ${establishResp.status()} — ${body.slice(0, 300)}`,
      )
    }

    await expect(state).toHaveAttribute('data-state', 'own', { timeout: 10_000 })

    // T3.23 shortened the displayed key to `first4…last4` — sixty-four hex
    // characters are unreadable and nobody compares them by eye. The full value
    // moved to `title`, so both properties are worth asserting: the key really
    // is the whole key, and the screen does not try to show it all.
    const npub = page.getByTestId('identity-npub')
    await expect(npub).toHaveAttribute('title', /^[0-9a-f]{64}$/)
    await expect(npub).toHaveText(/^[0-9a-f]{4}…[0-9a-f]{4}$/)
  })

  test('the account keeps working after the transition', async ({ page }) => {
    /** The platform no longer holds a key for this user. Everything that does
     *  not need one must still behave — a transition that quietly breaks the
     *  session would be worse than one that fails outright. */
    await needsAnAccountThatNeverEstablished(page)

    await page.goto('/profile/keys')
    await page.getByTestId('identity-start').click()
    await page.getByTestId('identity-generate').click()
    await page.getByTestId('identity-saved').check()
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/api/me/identity/establish') &&
          r.request().method() === 'POST',
        { timeout: 15_000 },
      ),
      page.getByTestId('identity-confirm').click(),
    ])

    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/dashboard/)

    await page.reload()
    await page.goto('/profile/keys')
    await expect(page.getByTestId('identity-state')).toHaveAttribute(
      'data-state',
      'own',
    )
  })
})
