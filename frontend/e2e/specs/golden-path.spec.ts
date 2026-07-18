import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/** Smoke #1 — register + walk through key logged-in routes.
 *  Loud on failure (helpers throw with HTTP status on non-2xx register). */
test('golden path: register + navigate main routes without crash', async ({ page }) => {
  test.setTimeout(60_000)

  const user = await registerUser(page, {
    email: uniqueEmail('e2e-c'),
    displayName: 'E2E Golden',
    canCarry: true,
  })

  // After register we should NOT be on login or register page.
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
