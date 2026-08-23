import { expect, test } from '@playwright/test'
import { signInFixed } from '../helpers'

/** Smoke #1 — sign in and walk through key logged-in routes.
 *
 *  Carrier mode, and not incidentally: `/trips/new` is a carrier's screen, and
 *  a sender is bounced off it. The old version got there by ticking a checkbox
 *  on the sign-up form, which read as a detail of registration; it was the
 *  whole reason the route rendered. */
test('golden path: sign in + navigate main routes without crash', async ({ page }) => {
  test.setTimeout(60_000)

  const user = await signInFixed(page, { mode: 'carrier' })

  // Signed in, so neither auth screen should hold us.
  await expect(page).not.toHaveURL(/\/(login|register)$/)

  // Trips + New-trip + Profile — each page must render actual content.
  for (const path of ['/trips', '/trips/new', '/profile']) {
    await page.goto(path)
    await page.waitForLoadState('domcontentloaded')
    const bodyText = (await page.locator('body').innerText()).trim()
    expect(bodyText.length, `empty body on ${path}`).toBeGreaterThan(50)
    expect(page.url(), `bounced off ${path}`).toContain(path)
  }

  console.log(`Golden smoke ok — user=${user.email}`)
})
