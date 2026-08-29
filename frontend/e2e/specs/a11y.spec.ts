import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { signInFixed } from '../helpers'

/**
 * T_TEST.8 — WCAG 2.2 AA on the five canonical pages.
 *
 * This closes the promise in DESIGNGUIDELINES §Accessibility, which until now
 * was a sentence with nothing behind it. axe checks what a machine can check —
 * contrast, names, roles, labels, focus order — which is maybe a third of AA.
 * The rest (does the focus order make sense, is the error message useful) still
 * needs a person. A green run here means "no machine-detectable violation",
 * and the suite says so rather than claiming the standard is met.
 *
 * Authenticated pages sign in as the long-lived e2e account (`E2E_USER` /
 * `E2E_PASSWORD`, owner's decision 2026-08-22). Registering through the UI is
 * code-based since T3.28 and cannot be automated; the previous helper drove a
 * form that had not existed for twelve days, and this spec was where that was
 * finally noticed.
 *
 * **Coverage is a moving target, and that is the point of listing it.** The five
 * canonical pages were the whole product in August; since then the deal screens,
 * the trip form and the panel were rebuilt, and the first run of this spec found
 * its defects in exactly the places it happened to look. What it looks at now:
 *
 *   covered — `/`, `/login`, `/register`, `/dashboard`, `/profile`, `/trips`,
 *             `/trips/new`, `/history`, `/disputes`
 *   not covered, and why:
 *     `/admin/params`  — needs a superuser, and this spec deliberately creates
 *                        only ordinary accounts. Audited by reading instead.
 *     `/carriers/:id`  — needs an existing carrier id; deriving one from the
 *                        board makes the test depend on the board not being
 *                        empty, which is a flaky test rather than a covered page.
 *     deal screens     — need two accounts and a matched deal; that is the smoke
 *                        suite's fixture, and sharing it here is its own task.
 */

const rules = JSON.parse(
  readFileSync(fileURLToPath(new URL('../axe-rules.json', import.meta.url)), 'utf-8'),
) as {
  tags: string[]
  disabled: { id: string; why: string }[]
}

const DISABLED = rules.disabled.map((r) => r.id)

/** Readable failure. The default assertion prints a JSON blob; what a person
 *  needs is which rule, how bad, and which element — in that order. */
function describe(violations: Awaited<ReturnType<AxeBuilder['analyze']>>['violations']): string {
  return violations
    .map((v) => {
      const nodes = v.nodes
        .slice(0, 3)
        .map((n) => `      ${n.target.join(' ')}`)
        .join('\n')
      const more = v.nodes.length > 3 ? `\n      …+${v.nodes.length - 3} more` : ''
      return `  [${v.impact ?? 'unknown'}] ${v.id} — ${v.help}\n${nodes}${more}\n      ${v.helpUrl}`
    })
    .join('\n\n')
}

async function scan(page: Page, label: string) {
  // `domcontentloaded` is not enough: half of these screens paint after their
  // first XHR, and axe would score an empty skeleton — the most accessible
  // page in the world is one with nothing on it.
  await page.waitForLoadState('networkidle')

  const results = await new AxeBuilder({ page })
    .withTags(rules.tags)
    .disableRules(DISABLED)
    .analyze()

  // Assert on a one-line-per-rule projection, not on the raw violations.
  // Passing the axe objects to `toEqual` made Playwright print its own diff of
  // the whole tree — hundreds of lines of nested `Object {}` per page, with the
  // readable message buried under it. The detail is still here, in the message;
  // what the diff shows is now the summary a person actually reads first.
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact ?? 'unknown'}) ×${v.nodes.length}`,
  )

  expect(
    summary,
    `${label} — ${results.violations.length} accessibility violation(s):\n\n${describe(results.violations)}\n`,
  ).toEqual([])
}

test.describe('accessibility (WCAG 2.2 AA, machine-checkable subset)', () => {
  test('landing', async ({ page }) => {
    await page.goto('/')
    await scan(page, '/')
  })

  // T_UX.23 — the three audience pages are public surfaces of their own, found
  // by their own searches. A landing that is scanned and two that are not is
  // the same page in three states of repair.
  test('carrier landing', async ({ page }) => {
    await page.goto('/carrier')
    await scan(page, '/carrier')
  })

  test('sender landing', async ({ page }) => {
    await page.goto('/send')
    await scan(page, '/send')
  })

  test('business landing', async ({ page }) => {
    await page.goto('/business')
    await scan(page, '/business')
  })

  // T3.11.03 — the rules directory is the most public surface the product has:
  // people arrive on it from a search engine, before they know what Vimana is.
  //
  // Scanned in its **empty state**, and deliberately: nothing is published in
  // the e2e database, and seeding a corpus here would make this spec depend on
  // fixture content that the corpus tasks will change under it. The empty state
  // is also the one a reader most often meets while the directory is young, and
  // a page that says "nothing here yet" still has a heading, a landmark and a
  // way onward — which is exactly what this scan is about.
  test('rules directory, empty corridor', async ({ page }) => {
    await page.goto('/rules/art/export/ru')
    await scan(page, '/rules/art/export/ru')
  })

  test('login', async ({ page }) => {
    await page.goto('/login')
    await scan(page, '/login')
  })

  test('register', async ({ page }) => {
    await page.goto('/register')
    await scan(page, '/register')
  })

  test('dashboard (authenticated)', async ({ page }) => {
    await signInFixed(page)
    await page.goto('/dashboard')
    // T_UX.23 — `/dashboard` is a redirect now: the panel lives at `/carrier`
    // or `/send` depending on the account's mode. Waiting for the real address
    // means axe scores the panel and not the instant before it.
    await page.waitForURL(/\/(carrier|send)$/)
    await scan(page, 'panel')
  })

  test('profile (authenticated)', async ({ page }) => {
    await signInFixed(page)
    await page.goto('/profile')
    await scan(page, '/profile')
  })

  test('trips board', async ({ page }) => {
    await signInFixed(page)
    await page.goto('/trips')
    await scan(page, '/trips')
  })

  test('new trip form (carrier)', async ({ page }) => {
    // The densest form in the product: eleven controls, and the one screen where
    // an unnamed field costs a carrier a published trip rather than a squint.
    await signInFixed(page, { mode: 'carrier' })
    await page.goto('/trips/new')
    await scan(page, '/trips/new')
  })

  test('history (authenticated)', async ({ page }) => {
    await signInFixed(page)
    await page.goto('/history')
    await scan(page, '/history')
  })

  test('disputes (authenticated)', async ({ page }) => {
    await signInFixed(page)
    await page.goto('/disputes')
    await scan(page, '/disputes')
  })
})
