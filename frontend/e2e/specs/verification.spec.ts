import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/**
 * Smoke #2 — Verification (T2.1) surface.
 *
 * Basic assertion: profile page has the VerificationSection with the
 * "self-verify" area for a fresh user. Full three-tier flow (peer request,
 * decline_polite banner from T_UX.1) requires two concurrent browser
 * contexts; kept as a follow-up when we split the spec.
 */
test('verification section renders on profile for a fresh user', async ({ page }) => {
  test.setTimeout(60_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-v'),
    displayName: 'E2E Verify',
  })

  await page.goto('/profile')
  await page.waitForLoadState('networkidle')
  await expect(
    page.getByText(/verification|верификация|верифікація|weryfikacja|vérification|verificación/i).first(),
  ).toBeVisible({ timeout: 10_000 })

  console.log(`Verification smoke ok for ${user.email}`)
})
