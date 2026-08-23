import { expect, test } from '@playwright/test'
import { signInFixed } from '../helpers'

/** Smoke #2 — the profile page renders visible content for a signed-in user.
 *
 *  It used to say "fresh user", and the account is no longer fresh. That costs
 *  nothing here: the assertion is that the screen renders and mentions what a
 *  profile mentions, which is true on day one and on day two hundred. Where
 *  freshness is actually load-bearing, the spec says so and cannot use this
 *  account at all — see `identity-establish`. */
test('profile page renders for a signed-in user', async ({ page }) => {
  test.setTimeout(45_000)
  const user = await signInFixed(page)

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
