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

    // Bob → /invite/<token>. AcceptInvitePage auto-triggers POST accept.
    // waitForResponse filter is method-strict to avoid matching CORS preflight
    // or a stray retry. If the response is non-2xx, log body — invaluable for
    // "Cannot accept your own invite" / "Invite already used" races.
    const [acceptResp] = await Promise.all([
      bobPage.waitForResponse(
        (r) =>
          r.url().includes(`/api/invites/${inviteBody.token}/accept`) &&
          r.request().method() === 'POST',
        { timeout: 15_000 },
      ),
      bobPage.goto(`/invite/${inviteBody.token}`),
    ])
    const acceptBody = await acceptResp.text().catch(() => '')
    if (!acceptResp.ok()) {
      throw new Error(`Accept invite failed HTTP ${acceptResp.status()} — ${acceptBody.slice(0, 200)}`)
    }

    // Wait for the actual success card by visible text, not body-scrape —
    // that way a stray double-render can't leave us reading the error state.
    await bobPage.waitForLoadState('domcontentloaded')
    await bobPage
      .getByText(/связь установлена|contact added|перейти в профиль/i)
      .waitFor({ timeout: 8_000 })
      .catch(async () => {
        const bodyDump = (await bobPage.locator('body').innerText()).slice(0, 200)
        throw new Error(
          `Accept UI never rendered success. Backend said HTTP ${acceptResp.status()} body=${acceptBody.slice(0, 100)}. Visible: ${bodyDump}`,
        )
      })

    // Symmetry check via API (not UI — ConnectionOut is nested and different
    // pages render display_name from different paths; the invariant we care
    // about is: each side has exactly the other in their connections list).
    const bobToken = await bobPage.evaluate(() => localStorage.getItem('token'))
    const aliceToken = await alicePage.evaluate(() => localStorage.getItem('token'))
    expect(bobToken, 'Bob localStorage token missing').toBeTruthy()
    expect(aliceToken, 'Alice localStorage token missing').toBeTruthy()

    const bobConns = await bobPage.request.get('/api/me/connections', {
      headers: { Authorization: `Bearer ${bobToken}` },
    })
    expect(bobConns.ok(), `Bob connections HTTP ${bobConns.status()}`).toBe(true)
    const bobConnsJson = (await bobConns.json()) as Array<{
      connected_user: { display_name: string; email?: string }
    }>
    const bobSeesAlice = bobConnsJson.some(
      (c) => c.connected_user.display_name === alice.displayName,
    )
    expect(bobSeesAlice, `Bob does not see Alice. Got: ${JSON.stringify(bobConnsJson).slice(0, 200)}`).toBe(true)

    const aliceConns = await alicePage.request.get('/api/me/connections', {
      headers: { Authorization: `Bearer ${aliceToken}` },
    })
    expect(aliceConns.ok(), `Alice connections HTTP ${aliceConns.status()}`).toBe(true)
    const aliceConnsJson = (await aliceConns.json()) as Array<{
      connected_user: { display_name: string }
    }>
    const aliceSeesBob = aliceConnsJson.some(
      (c) => c.connected_user.display_name === bob.displayName,
    )
    expect(aliceSeesBob, `Alice does not see Bob. Got: ${JSON.stringify(aliceConnsJson).slice(0, 200)}`).toBe(true)

    console.log(`Invite flow ok — alice=${alice.email}, bob=${bob.email}, token=${inviteBody.token.slice(0, 12)}…`)
  } finally {
    await aliceContext.close()
    await bobContext.close()
  }
})
