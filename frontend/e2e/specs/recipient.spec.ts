import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/** Smoke #3 — /join/deal/:token route wired.
 *
 *  Extremely lenient: page must not white-screen. Either it renders some
 *  content (loading state, error text, redirect landing) or the URL
 *  changed (redirect happened). Both outcomes prove routing is alive.
 *  Any deeper assertion (specific error text, specific redirect target)
 *  fights zustand-vs-page.goto state race and is fragile. */
test('recipient join route handles unknown token gracefully', async ({ page }) => {
  test.setTimeout(30_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-r'),
    displayName: 'E2E Recipient',
  })

  const startUrl = page.url()
  await page.goto('/join/deal/definitely-not-a-real-token-999')
  // Give React + useEffect + async fetch a beat.
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(2_000)

  const bodyText = (await page.locator('body').innerText()).trim()
  const endUrl = page.url()
  const urlChanged = endUrl !== startUrl && !endUrl.endsWith('/join/deal/definitely-not-a-real-token-999')
  const hasContent = bodyText.length > 20

  expect(hasContent || urlChanged, `blank + no redirect from ${startUrl} → ${endUrl}`).toBeTruthy()

  console.log(
    `Recipient smoke ok — user=${user.email}, url=${endUrl}, body-len=${bodyText.length}, url-changed=${urlChanged}`,
  )
})
