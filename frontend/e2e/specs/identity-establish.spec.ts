import { expect, test } from '@playwright/test'
import { registerUser } from '../helpers'

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
 * a regression rather than a test defect. `registerUser` mints a unique
 * `@e2e.vimana.local` address, which the nightly cleanup prunes.
 *
 * The NIP-07 branch is not covered here — a real extension needs a persistent
 * context (see T_TEST.3 notes). The browser-generated branch is the default
 * path and the one carrying the crypto risk.
 */
test.describe('identity: establish', () => {
  test('generates a key in the browser and the backend accepts it', async ({
    page,
  }) => {
    await registerUser(page)

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
    await expect(page.getByTestId('identity-npub')).toHaveText(/^[0-9a-f]{64}$/)
  })

  test('the account keeps working after the transition', async ({ page }) => {
    /** The platform no longer holds a key for this user. Everything that does
     *  not need one must still behave — a transition that quietly breaks the
     *  session would be worse than one that fails outright. */
    await registerUser(page)

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
