import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/**
 * Smoke #2 — Verification / Profile surface.
 *
 * Just proves the profile page renders with the expected structural bits
 * (identity/verification-related content is present in the DOM in some form).
 * Full 3-tier verification flow requires two concurrent contexts — pt.2.
 */
test('profile page renders for a fresh user (verification surface present)', async ({ page }) => {
  test.setTimeout(60_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-v'),
    displayName: 'E2E Verify',
  })

  await page.goto('/profile')
  await page.waitForLoadState('networkidle')

  // Body must have visible content — no blank/broken page.
  const bodyText = (await page.locator('body').innerText()).trim()
  expect(bodyText.length).toBeGreaterThan(50)

  // Very defensive: some string mentioning identity/verify/verify-related
  // concepts, or at least the app's display name. Full i18n coverage lives
  // in vitest, not here.
  expect(bodyText.toLowerCase()).toMatch(/vimana|profile|email|password|nostr|verif|верификация|верифікація|verificación|weryfikacja|vérification|identity/i)

  console.log(`Verification smoke ok for ${user.email}`)
})
