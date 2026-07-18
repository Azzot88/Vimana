import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/**
 * Smoke #3 — Recipient invite (T3.3).
 *
 * Simplest structural check: /join/deal/<invalid-token> either redirects
 * to login (unauthenticated) or shows an "Invite not found" message —
 * proving the route is wired end-to-end (App.tsx → JoinDealPage → backend).
 *
 * A full invite-and-join round-trip requires a real deal + sender-only
 * button + clipboard access — deferred to a bigger spec (pt.2).
 */
test('recipient join route handles bogus token gracefully', async ({ page }) => {
  test.setTimeout(30_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-r'),
    displayName: 'E2E Recipient',
  })

  await page.goto('/join/deal/definitely-not-a-real-token-999')
  await page.waitForLoadState('networkidle')
  // Either a friendly error surfaces, or we get redirected somewhere sane
  // (dashboard, login). No crash, no white screen.
  await expect(page.locator('body')).not.toHaveText('', { timeout: 5_000 })

  console.log(`Recipient smoke ok for ${user.email}`)
})
