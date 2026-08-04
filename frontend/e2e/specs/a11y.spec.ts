import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { registerUser } from '../helpers'

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
 * Two of the five pages need a session, so this spec registers a user the same
 * way the smoke suite does: `…@e2e.vimana.local`, pruned by `cleanup_e2e_users`.
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

  test('login', async ({ page }) => {
    await page.goto('/login')
    await scan(page, '/login')
  })

  test('register', async ({ page }) => {
    await page.goto('/register')
    await scan(page, '/register')
  })

  test('dashboard (authenticated)', async ({ page }) => {
    await registerUser(page)
    await page.goto('/dashboard')
    await scan(page, '/dashboard')
  })

  test('profile (authenticated)', async ({ page }) => {
    await registerUser(page)
    await page.goto('/profile')
    await scan(page, '/profile')
  })
})
