import { expect, test } from '@playwright/test'
import { registerUser, uniqueEmail } from '../helpers'

/** Multi-context #1 — invite copy-paste between two independent browser
 *  contexts (isolated cookies + localStorage). Alice creates an invite link,
 *  Bob (fresh session) opens it, connection is established both directions.
 *
 *  Runs against prod. Test users are cleaned up daily by the Celery task. */
test('invite flow: Alice creates → Bob accepts → connection visible', async ({ browser }) => {
  test.setTimeout(90_000)

  const aliceContext = await browser.newContext()
  const bobContext = await browser.newContext()
  const alicePage = await aliceContext.newPage()
  const bobPage = await bobContext.newPage()

  try {
    const alice = await registerUser(alicePage, {
      email: uniqueEmail('e2e-alice'),
      displayName: 'E2E Alice',
    })
    const bob = await registerUser(bobPage, {
      email: uniqueEmail('e2e-bob'),
      displayName: 'E2E Bob',
    })

    // Alice → /invite → click "Создать ссылку" → capture token from the XHR.
    await alicePage.goto('/invite')
    await alicePage.waitForLoadState('domcontentloaded')

    const [createResp] = await Promise.all([
      alicePage.waitForResponse(
        (r) =>
          r.url().includes('/api/invites') &&
          !r.url().includes('/mine') &&
          !r.url().includes('/accept') &&
          r.request().method() === 'POST',
        { timeout: 10_000 },
      ),
      alicePage
        .getByRole('button', { name: /создать ссылку|create link|створити|utwórz|créer|crear/i })
        .first()
        .click(),
    ])
    expect(createResp.ok(), `create invite failed HTTP ${createResp.status()}`).toBe(true)
    const inviteBody = (await createResp.json()) as { token: string }
    expect(inviteBody.token, 'no token in invite response').toBeTruthy()

    // Bob → /invite/<token>. AcceptInvitePage auto-triggers the POST accept.
    const [acceptResp] = await Promise.all([
      bobPage.waitForResponse(
        (r) => r.url().includes(`/api/invites/${inviteBody.token}/accept`),
        { timeout: 15_000 },
      ),
      bobPage.goto(`/invite/${inviteBody.token}`),
    ])
    expect(acceptResp.ok(), `accept invite failed HTTP ${acceptResp.status()}`).toBe(true)

    // Success UI: green checkmark card with "Связь установлена" or similar.
    await bobPage.waitForLoadState('domcontentloaded')
    await bobPage.waitForTimeout(1_000)
    const successText = (await bobPage.locator('body').innerText()).toLowerCase()
    expect(successText).toMatch(/связь установлена|contact|profile|перейти в профиль/i)

    // Bob → /profile → connections list must include Alice by display name.
    await bobPage.goto('/profile')
    await bobPage.waitForLoadState('domcontentloaded')
    await bobPage.waitForResponse(
      (r) => r.url().includes('/api/social/connections') && r.request().method() === 'GET',
      { timeout: 10_000 },
    )
    await bobPage.waitForTimeout(500)
    const bobProfileText = await bobPage.locator('body').innerText()
    expect(bobProfileText, 'Alice not visible in Bob connections').toContain(alice.displayName)

    // Symmetry: Alice → /profile should now show Bob too.
    await alicePage.goto('/profile')
    await alicePage.waitForLoadState('domcontentloaded')
    await alicePage.waitForResponse(
      (r) => r.url().includes('/api/social/connections') && r.request().method() === 'GET',
      { timeout: 10_000 },
    )
    await alicePage.waitForTimeout(500)
    const aliceProfileText = await alicePage.locator('body').innerText()
    expect(aliceProfileText, 'Bob not visible in Alice connections').toContain(bob.displayName)

    console.log(`Invite flow ok — alice=${alice.email}, bob=${bob.email}, token=${inviteBody.token.slice(0, 12)}…`)
  } finally {
    await aliceContext.close()
    await bobContext.close()
  }
})
