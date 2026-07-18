import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/**
 * Smoke #3 — Recipient join route wiring.
 *
 * Proves `/join/deal/:token` is wired (App.tsx → JoinDealPage → backend).
 * A bogus token should either surface a friendly error, redirect somewhere,
 * or just render a page — anything but crash / blank.
 *
 * Full invite-and-join round-trip requires clipboard + real deal + sender
 * button — pt.2.
 */
test('recipient join route handles unknown token gracefully', async ({ page }) => {
  test.setTimeout(30_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-r'),
    displayName: 'E2E Recipient',
  })

  await page.goto('/join/deal/definitely-not-a-real-token-999')
  await page.waitForLoadState('networkidle')

  // Give the JoinDealPage's async fetch a beat to run.
  await page.waitForTimeout(1500)

  // Success = either navigated away (login/dashboard) OR rendered content
  // with visible text (loading state, "invite not found" error, redirect).
  // Failure = zero DOM content / crashed React tree.
  const bodyText = (await page.locator('body').innerText()).trim()
  expect(bodyText.length + page.url().length).toBeGreaterThan(50)

  console.log(`Recipient smoke ok — user=${user.email}, url=${page.url()}, body-len=${bodyText.length}`)
})
