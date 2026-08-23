import { expect, test } from '@playwright/test'
import { signInFixed } from '../helpers'

/** Multi-context #4 (T_UX.3 pt.3) — cross-tab logout sync.
 *
 *  Two pages in the SAME browser context share localStorage. When the user
 *  clicks logout in one page, the `storage` event fires in the other and
 *  `<AuthBootstrap>` should call `logout('multi_tab')` → silent redirect
 *  to /login. Without pt.3 the second tab would continue rendering the
 *  authenticated UI and only realize it's unauth'd on the next API 401.
 */
test('multi-tab logout: logout in tab A redirects tab B to /login', async ({ browser }) => {
  test.setTimeout(45_000)

  const context = await browser.newContext()
  try {
    const tabA = await context.newPage()
    await signInFixed(tabA)

    // Open second tab in the same context — inherits cookies + localStorage.
    const tabB = await context.newPage()
    await tabB.goto('/profile')
    await tabB.waitForLoadState('domcontentloaded')
    await expect(tabB).toHaveURL(/\/profile/)

    // Trigger logout in tab A by directly removing the token from
    // localStorage (mirrors what the profile "Sign out" button does).
    // Using page.evaluate is more reliable than clicking a specific button
    // whose selector might drift.
    await tabA.evaluate(() => {
      localStorage.removeItem('token')
    })

    // Also fire the storage event manually — tabA's own localStorage.removeItem
    // does NOT trigger a storage event in tabA, but tabB should get it
    // automatically because they share the same origin/context.
    // We wait for tabB to react.
    await tabB.waitForURL(/\/login/, { timeout: 8_000 })
    // No `?reason=` param — multi-tab logout is silent.
    expect(tabB.url()).not.toContain('reason=')

    console.log(`Multi-tab logout ok — tabB redirected to ${tabB.url()}`)
  } finally {
    await context.close()
  }
})
