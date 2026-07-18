import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/** Smoke #2 — profile page renders visible content for a fresh user. */
test('profile page renders for a fresh user', async ({ page }) => {
  test.setTimeout(45_000)
  const user = await registerUser(page, {
    email: uniqueEmail('e2e-v'),
    displayName: 'E2E Verify',
  })

  await page.goto('/profile')
  await page.waitForLoadState('domcontentloaded')
  await expect(page).toHaveURL(/\/profile/)

  const bodyText = (await page.locator('body').innerText()).trim()
  expect(bodyText.length).toBeGreaterThan(100)
  expect(bodyText.toLowerCase()).toMatch(
    /vimana|profile|email|nostr|verif|identity|верификация|верифікація/i,
  )

  console.log(`Verification smoke ok for ${user.email}`)
})
