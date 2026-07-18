import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/** Smoke #3 — /join/deal/:token wiring works for bogus tokens. */
test('recipient join route handles unknown token gracefully', async ({ page }) => {
  test.setTimeout(30_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-r'),
    displayName: 'E2E Recipient',
  })

  // Watch the real /api/deals/join/... XHR — must respond 4xx (bogus token).
  const [joinResp] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/deals/join/') && r.request().method() === 'POST',
      { timeout: 10_000 },
    ),
    page.goto('/join/deal/definitely-not-a-real-token-999'),
  ])
  expect(joinResp.status(), 'bogus token should be 4xx').toBeGreaterThanOrEqual(400)
  expect(joinResp.status()).toBeLessThan(500)

  await page.waitForLoadState('domcontentloaded')
  const bodyText = (await page.locator('body').innerText()).trim()
  expect(bodyText.length, 'page should not be blank').toBeGreaterThan(20)

  console.log(
    `Recipient smoke ok — user=${user.email}, join-status=${joinResp.status()}, body-len=${bodyText.length}`,
  )
})
