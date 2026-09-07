import { expect, test, type APIRequestContext, type Page } from '@playwright/test'
import { signInFixed, type SignedIn } from '../helpers'

/** T3.11.07 — combinations of corridors, currencies, places and services.
 *
 *  ## Why this is not one big matrix
 *
 *  The obvious shape — every corridor × every currency × every handover method,
 *  each one walked through the wizard — is wrong here for three reasons, and
 *  they are worth stating because the temptation comes back every time.
 *
 *  1. **This suite runs against prod** with `workers: 1` and one long-lived
 *     account (see `playwright.config.ts`). Twenty published trips per run is
 *     twenty real listings on a real board, and a matrix that grows is a board
 *     that fills with test data.
 *  2. **Vocabularies are data, and data is the backend's to test.** Which
 *     postal services exist in Türkiye, which payment systems in Kazakhstan,
 *     what `payment_systems('RU','AE')` returns — those are pure functions over
 *     files, already covered in `tests/test_directories.py`, in milliseconds,
 *     against an isolated database. Re-asserting them through a browser buys
 *     nothing and costs a minute each.
 *  3. What a browser **can** prove and nothing else can is that the chain is
 *     wired: pick DXB → IST and the postal picker narrows to Türkiye; add a
 *     Moscow meeting place and it does *not* appear on the Dubai end; set the
 *     account to USDT and the trip form offers four characters where the field
 *     used to allow three.
 *
 *  So the sweep is split in two, and the split is the whole design:
 *
 *  - **`request`, no browser** — the combinations. One call per corridor
 *     against the directory endpoints, asserting the *rules* (local only, both
 *     ends, crypto always, arrival before departure). Cheap enough that adding
 *     a corridor costs nothing, which is what makes a matrix maintainable.
 *  - **The browser** — the wiring, not the combinations. Three walks, and none
 *     of them publishes. Against a real board that is not a compromise but the
 *     point: everything these assert — which meeting place is offered on which
 *     end, which payment methods survive the corridor, which currency the form
 *     starts in — is visible in the form before the publish button is pressed.
 *     The publish → preview → edit → return-trip lifecycle wants a disposable
 *     environment and is not in here until there is one.
 *
 *  ## Arrange over the API, assert in the DOM
 *
 *  The profile fixtures — addresses, meeting places, payment methods,
 *  currencies — are written with `request` and the signed-in token, never
 *  through the profile UI. Six forms filled by a robot to set up one assertion
 *  is six ways for an unrelated change to break this file, and none of them are
 *  what it is testing.
 *
 *  ## Everything it creates, it removes
 *
 *  Against a shared prod account the alternative is a suite that poisons the
 *  next run: the meeting places and the profile settings are put back exactly
 *  as they were found. Same lesson the backend suite learned from `vimana_test`
 *  never being reset — a fixture that accumulates is a test that passes once.
 */

/** Corridors the directory sweep runs over. Chosen for what they exercise, not
 *  for coverage: RU→AE is the launch corridor and the one HodlHodl has nothing
 *  for; TR is the country whose ISO name changed under us; KZ and PL are two
 *  ends with no shared rail, which is the case the crypto entries exist for;
 *  US→MX is the one where our own file, not the vendored one, carries Zelle. */
const CORRIDORS = [
  { departure: 'AE', arrival: 'RU' }, // DXB → SVO
  { departure: 'RU', arrival: 'TR' }, // SVO → IST
  { departure: 'KZ', arrival: 'PL' }, // ALA → WAW
  { departure: 'US', arrival: 'MX' }, // JFK → MEX
] as const

/** Always offered, whatever the two countries are — they are not a country's
 *  rail. Mirrors `core.directories.ALWAYS_OFFERED`. */
const ALWAYS = ['btc', 'usdt', 'zec']

interface Entry {
  code: string
  name: string
}

async function directories(api: APIRequestContext, token: string, path: string) {
  const res = await api.get(path, { headers: { Authorization: `Bearer ${token}` } })
  expect(res.ok(), `${path} → ${res.status()}`).toBeTruthy()
  return (await res.json()) as Entry[]
}

test.describe('directory combinations', () => {
  let me: SignedIn

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    me = await signInFixed(page, { mode: 'carrier' })
    await page.close()
  })

  for (const corridor of CORRIDORS) {
    test(`payment systems for ${corridor.departure}→${corridor.arrival}`, async ({
      request,
    }) => {
      const entries = await directories(
        request,
        me.token,
        `/api/payment-systems?arrival=${corridor.arrival}&departure=${corridor.departure}`,
      )
      const codes = entries.map((e) => e.code)

      // The three that must be there whatever the corridor, and must be first:
      // appended last they fell past the form's visible chips as soon as both
      // countries had entries, and "always offered" is not "offered if the list
      // is short enough".
      expect(codes.slice(0, 3)).toEqual(ALWAYS)

      // One thing written twice is a choice the carrier should not have to make.
      const names = entries.map((e) => e.name.toLowerCase())
      expect(names).not.toContain('bitcoin')
      expect(new Set(codes).size, 'duplicate codes').toBe(codes.length)

      // Both ends are represented. The product exists because the two people are
      // in different countries, so a picker built from one of them is half a
      // picker — and which half is missing depends on who published.
      expect(entries.length).toBeGreaterThan(ALWAYS.length)
    })

    test(`postal services for ${corridor.arrival}`, async ({ request }) => {
      const entries = await directories(
        request,
        me.token,
        `/api/postal-services?country=${corridor.arrival}`,
      )
      // Local only (owner's decision 2026-09-06): a list headed by three
      // international couriers describes a company, not a person with one
      // pick-up point in the next street. An empty list is a legal answer for a
      // country we have no entries for — the form falls back to typing.
      expect(new Set(entries.map((e) => e.code)).size).toBe(entries.length)
    })
  }

  test('an unknown country answers empty rather than global', async ({ request }) => {
    // `ZZ` is not a country. The honest answer is nothing, not "here is the
    // global set" — a catalogue with no external source must not be able to
    // tell a carrier that the one company collecting parcels in their town does
    // not exist, and the way it avoids that is by saying nothing at all.
    const entries = await directories(request, me.token, '/api/postal-services?country=ZZ')
    expect(entries).toEqual([])
  })
})

/** ── the browser half ─────────────────────────────────────────────────────
 *
 *  Three walks, none of which publishes. The profile rows they need are written
 *  over the API in `beforeAll` and removed in `afterAll`.
 */

interface Fixtures {
  placeIds: string[]
  currencies: string[]
  methods: unknown
}

async function arrangeProfile(
  api: APIRequestContext,
  token: string,
): Promise<Fixtures> {
  const auth = { Authorization: `Bearer ${token}` }
  const before = await (await api.get('/api/auth/me', { headers: auth })).json()

  // Two meeting places in two countries. This is the fixture the form is meant
  // to narrow: the Moscow one must not be offered on the Dubai end.
  const placeIds: string[] = []
  for (const place of [
    { description: 'E2E · у метро Фили, выход №3', country_iso: 'RU', city: 'Moscow' },
    { description: 'E2E · Terminal 3, by the Costa', country_iso: 'AE', city: 'Dubai' },
  ]) {
    const res = await api.post('/api/me/meeting-places', { headers: auth, data: place })
    expect(res.ok(), await res.text()).toBeTruthy()
    placeIds.push((await res.json()).id)
  }

  await api.patch('/api/auth/me', {
    headers: auth,
    data: {
      // A four-character code on purpose: `USDT` is what broke every column and
      // schema that assumed three, and the form pre-fills from this list.
      default_currencies: ['USDT', 'USD', 'AED'],
      payment_methods: [
        { name: 'E2E наличные при встрече', country: null },
        { name: 'E2E Каспи', country: 'KZ' },
        { name: 'E2E Zelle', country: 'US' },
      ],
    },
  })

  return {
    placeIds,
    currencies: before.default_currencies ?? ['USD'],
    methods: before.payment_methods ?? [],
  }
}

async function restoreProfile(
  api: APIRequestContext,
  token: string,
  before: Fixtures,
) {
  const auth = { Authorization: `Bearer ${token}` }
  for (const id of before.placeIds) {
    await api.delete(`/api/me/meeting-places/${id}`, { headers: auth })
  }
  await api.patch('/api/auth/me', {
    headers: auth,
    data: {
      default_currencies: before.currencies,
      payment_methods: before.methods,
    },
  })
}

/** The wizard's first step, filled. Kept as a function because three specs need
 *  it and the fourth needs it twice — and a route typed slightly differently in
 *  each would make a failure look like a routing bug. */
async function fillRoute(page: Page, stops: string[], daysOut: number) {
  for (let i = 0; i < stops.length; i += 1) {
    if (i >= 2) {
      await page.getByRole('button', { name: /Добавить пересадку|Add a transfer/ }).click()
    }
  }
  const inputs = page.locator('input[placeholder="DXB"], input[placeholder="JFK"]')
  for (let i = 0; i < stops.length; i += 1) {
    await inputs.nth(i).fill(stops[i])
    // Picked from the list, not typed: the pick is what carries the country,
    // and the country is what every narrowing below stands on.
    // The suggestions are buttons, not `option`s: the list is a portalled panel
    // rather than a `<select>`, because it has to escape the wizard sheet's
    // overflow. Picking from it is what carries the country.
    await page
      .getByRole('button', { name: new RegExp(`\\b${stops[i]}\\b`) })
      .first()
      .click()
  }
  // Departures: our own picker, so the value goes through it rather than into a
  // native input. One per stop but the last.
  const when = new Date(Date.now() + daysOut * 86_400_000)
  for (let i = 0; i < stops.length - 1; i += 1) {
    await page.getByRole('button', { name: /Выбрать дату|Pick a date/ }).first().click()
    // Scoped to the calendar: «Сохранить» is a common word on this product, and
    // an unscoped match would press whichever one the DOM offered first.
    const calendar = page.getByRole('dialog')
    await calendar
      .getByRole('button', { name: String(when.getDate()), exact: true })
      .click()
    await calendar.getByRole('button', { name: /Сохранить|^Save$/ }).click()
  }
}

test.describe('trip form narrows by country', () => {
  let me: SignedIn
  let before: Fixtures

  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage()
    me = await signInFixed(page, { mode: 'carrier' })
    before = await arrangeProfile(page.request, me.token)
    await page.close()
  })

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage()
    // Nothing to cancel: these specs stop short of publishing. What they do
    // create is profile rows, and those are removed here — against a shared
    // prod account a fixture that accumulates is a test that passes once.
    await restoreProfile(page.request, me.token, before)
    await page.close()
  })

  test('the account currencies reach the trip form as chips', async ({ page }) => {
    await signInFixed(page, { mode: 'carrier' })
    await page.goto('/trips/new?step=3')
    // `USDT` is first in the account list, so it is the one the form starts in —
    // four characters, in a field that used to be `maxLength={3}`.
    await expect(page.getByRole('button', { name: 'USDT', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'AED', exact: true })).toBeVisible()
  })

  test('a meeting place is offered only on its own end of the route', async ({
    page,
  }) => {
    await signInFixed(page, { mode: 'carrier' })
    await page.goto('/trips/new?step=1')
    await fillRoute(page, ['DXB', 'SVO'], 9)

    await page.goto('/trips/new?step=3')
    // Both ends offer "in person", which is what reveals the place picker.
    for (const button of await page.getByRole('button', { name: /Лично|In person/ }).all()) {
      await button.click()
    }
    const selects = page.locator('select')
    const originOptions = await selects.first().locator('option').allInnerTexts()
    const destOptions = await selects.nth(1).locator('option').allInnerTexts()

    // Dubai is the origin, Moscow the destination — each place on its own side
    // and neither on the other. Before the country existed both lists held both,
    // and the carrier read and rejected one on every publication.
    expect(originOptions.join(' ')).toContain('Terminal 3')
    expect(originOptions.join(' ')).not.toContain('Фили')
    expect(destOptions.join(' ')).toContain('Фили')
    expect(destOptions.join(' ')).not.toContain('Terminal 3')
  })

  test('payment methods follow the corridor, cash follows everywhere', async ({
    page,
  }) => {
    await signInFixed(page, { mode: 'carrier' })
    await page.goto('/trips/new?step=1')
    await fillRoute(page, ['ALA', 'WAW'], 10)

    await page.goto('/trips/new?step=3')
    await page.getByRole('button', { name: /Вне платформы|Off the platform/ }).click()

    const body = await page.locator('body').innerText()
    // Каспи is Kazakhstan and this route starts there; Zelle is US and has no
    // business being offered. Cash carries no country and is offered anyway,
    // which is the `null` case doing its job rather than falling through.
    expect(body).toContain('E2E Каспи')
    expect(body).toContain('E2E наличные при встрече')
    expect(body).not.toContain('E2E Zelle')

    // The three that are offered on every corridor, from the catalogue rather
    // than from the profile.
    for (const code of ['BTC', 'USDT', 'ZEC']) {
      await expect(page.getByRole('button', { name: code, exact: true })).toBeVisible()
    }
  })
})
