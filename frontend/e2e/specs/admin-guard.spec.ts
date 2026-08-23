import { expect, test } from '@playwright/test'
import { signInFixed } from '../helpers'

/** Multi-context #3 — access control for admin routes.
 *
 *  An ordinary user has role='user' and must NOT reach any of the three admin
 *  pages. Each page guards with `<Navigate to="/dashboard" />` when the current
 *  user is not superuser (arbiter for /admin/disputes).
 *
 *  Also verifies the AdminPanelSection Bento card on /profile is hidden for
 *  regular users — no discoverability leak.
 *
 *  **This spec is why the long-lived account must stay `role='user'`.** It read
 *  as a free property when every run minted a new account; now it is a standing
 *  requirement on shared state, and promoting the e2e account to arbiter or
 *  superuser turns this test red. That failure is correct — it means the thing
 *  being asserted stopped being true — but it will look like a guard regression,
 *  so the cause is written here rather than rediscovered. */
test('admin guard: regular user is redirected away from admin routes', async ({ browser }) => {
  test.setTimeout(75_000)

  const context = await browser.newContext()
  const page = await context.newPage()

  try {
    const user = await signInFixed(page)

    // Regular user should see NO admin panel section on their profile.
    await page.goto('/profile')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(500)
    const profileText = await page.locator('body').innerText()
    expect(profileText, 'admin panel leaked to regular user').not.toMatch(
      /administration|администрирование/i,
    )

    // Each admin path must bounce off to a non-admin route (typically
    // /dashboard). We assert URL no longer contains /admin/ after nav settles.
    for (const path of ['/admin/notices', '/admin/users', '/admin/disputes']) {
      await page.goto(path)
      await page.waitForLoadState('domcontentloaded')
      // Give React Router the <Navigate replace> beat.
      await page.waitForTimeout(700)
      const endUrl = page.url()
      expect(endUrl, `regular user reached ${path}`).not.toContain('/admin/')
    }

    console.log(`Admin guard ok — user=${user.email}`)
  } finally {
    await context.close()
  }
})
