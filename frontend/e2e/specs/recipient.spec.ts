import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/** Smoke #3 — /join/deal/:token route is wired.
 *
 *  Two acceptable outcomes:
 *  - App still has the auth from registration → JoinDealPage hits
 *    `/api/deals/join/<token>` and gets 4xx. XHR is observable.
 *  - App reload cleared the in-memory auth store (Playwright page.goto is
 *    a hard nav; zustand doesn't rehydrate) → JoinDealPage redirects to
 *    /login?next=... . No XHR, but redirect is the correct behaviour.
 *
 *  We race the two — whichever happens first, test passes. Failure = white
 *  screen (React crash / broken route). */
test('recipient join route handles unknown token gracefully', async ({ page }) => {
  test.setTimeout(30_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-r'),
    displayName: 'E2E Recipient',
  })

  const bogus = 'definitely-not-a-real-token-999'
  const result = await Promise.race([
    // Path A: authenticated → XHR fires and returns 4xx.
    page
      .waitForResponse(
        (r) => r.url().includes('/api/deals/join/') && r.request().method() === 'POST',
        { timeout: 8_000 },
      )
      .then((r) => ({ kind: 'xhr' as const, status: r.status() })),
    // Path B: unauthenticated → redirected to /login.
    page
      .waitForURL(/\/login/, { timeout: 8_000 })
      .then(() => ({ kind: 'redirect' as const, status: 0 })),
    page.goto(`/join/deal/${bogus}`).then(() => ({ kind: 'nav' as const, status: 0 })),
  ])

  // The `nav` outcome by itself is not a proof — one of the other two must
  // also fire within a short follow-up window.
  if (result.kind === 'nav') {
    const settled = await Promise.race([
      page
        .waitForResponse(
          (r) => r.url().includes('/api/deals/join/') && r.request().method() === 'POST',
          { timeout: 5_000 },
        )
        .then((r) => ({ kind: 'xhr' as const, status: r.status() })),
      page
        .waitForURL(/\/login/, { timeout: 5_000 })
        .then(() => ({ kind: 'redirect' as const, status: 0 })),
    ]).catch(() => null)
    expect(settled, 'expected either XHR or redirect after page load').not.toBeNull()
    if (settled?.kind === 'xhr') {
      expect(settled.status).toBeGreaterThanOrEqual(400)
      expect(settled.status).toBeLessThan(500)
    }
  } else if (result.kind === 'xhr') {
    expect(result.status).toBeGreaterThanOrEqual(400)
    expect(result.status).toBeLessThan(500)
  }
  // redirect kind — no extra assertion; being on /login is proof enough.

  await page.waitForLoadState('domcontentloaded')
  const bodyText = (await page.locator('body').innerText()).trim()
  expect(bodyText.length, 'page must not be blank').toBeGreaterThan(20)

  console.log(
    `Recipient smoke ok — user=${user.email}, outcome=${result.kind}, url=${page.url()}`,
  )
})
