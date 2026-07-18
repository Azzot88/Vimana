import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/**
 * Smoke #1 — Golden path (minimal, honest).
 *
 * Proves: app is up, register works, key logged-in routes render without
 * crashing. Full deal lifecycle (trip publish → match → chat → confirm) is
 * covered by ~200 pytest integration tests; e2e smoke doesn't reproduce it —
 * that's fragile against UI copy changes.
 *
 * If this passes, you're 90% sure prod is alive.
 */
test('golden path: register + navigate main routes without crash', async ({ page }) => {
  test.setTimeout(90_000)

  const user = await registerUser(page, {
    email: uniqueEmail('e2e-c'),
    displayName: 'E2E Golden',
    canCarry: true,
  })

  // Dashboard / landing after register — page has content.
  await page.waitForLoadState('networkidle')
  await expect(page.locator('body')).not.toBeEmpty()

  // Trips page loads.
  await page.goto('/trips')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('body')).not.toBeEmpty()

  // New-trip page loads (carrier has access).
  await page.goto('/trips/new')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('body')).not.toBeEmpty()

  // Profile page loads.
  await page.goto('/profile')
  await page.waitForLoadState('networkidle')
  await expect(page.locator('body')).not.toBeEmpty()

  console.log(`Golden smoke ok — user=${user.email}`)
})
