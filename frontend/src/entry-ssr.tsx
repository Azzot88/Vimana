import type { ReactElement } from 'react'
import { renderToString } from 'react-dom/server'
import { Route, Routes } from 'react-router-dom'
import { StaticRouter } from 'react-router-dom/server'
import { I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import LandingPage from './pages/LandingPage'
import CarrierLandingPage from './pages/CarrierLandingPage'
import SenderLandingPage from './pages/SenderLandingPage'
import BusinessLandingPage from './pages/BusinessLandingPage'
import RulesPage from './pages/RulesPage'
import RulesIndexPage from './pages/RulesIndexPage'

/**
 * T_UX.7 pt.2 — the landing, rendered to HTML at build time.
 * T_UX.23 — four of them now.
 *
 * Only the public pages. The rest of the product is behind a session and has
 * nothing to prerender: an empty dashboard shell in the HTML would help no
 * crawler and would have to be kept in sync with the real one forever.
 *
 * **The audience pages are prerendered as their guest half.** `/carrier` and
 * `/send` show the panel to a signed-in account, but there is no session in
 * Node — the store reads a `localStorage` that does not exist and comes up
 * anonymous — so what is rendered here is exactly what a first-time visitor and
 * a crawler get. That is also what hydration then matches, which is the part
 * that would break loudly if it were otherwise. The components are named
 * directly rather than routed through `ModeHomePage` so this stays true by
 * construction instead of by luck.
 *
 * `StaticRouter` rather than `BrowserRouter` because there is no history in
 * Node. Each path is rendered separately and written to its own file; nginx
 * serves each one at exactly its address (see `nginx.conf`).
 *
 * Russian only, deliberately — see `scripts/prerender.mjs`.
 */

const PAGES: Record<string, () => ReactElement> = {
  '/': () => <LandingPage />,
  '/carrier': () => <CarrierLandingPage />,
  '/send': () => <SenderLandingPage />,
  '/business': () => <BusinessLandingPage />,
}

/** The paths this build can prerender, read by `scripts/prerender.mjs` so the
 *  list lives in one place and a page added here cannot be forgotten there. */
export const PRERENDER_PATHS = Object.keys(PAGES)

/**
 * T3.11.03 — a rules page, rendered from data fetched at build time.
 *
 * Separate from `render` because these paths are not a fixed list: they come
 * from whatever is published in the database when the build runs. The data is
 * passed in rather than fetched here — Node has no session, no axios base URL
 * and no business knowing where the API lives; `scripts/prerender.mjs` does.
 *
 * ⚠️ **What this does and does not solve.** A set published after the last
 * deploy has no file, and nginx falls back to the SPA shell: the page works for
 * a person and is empty for a crawler until the next build. That is variant A,
 * chosen deliberately (`IMPLEMENTATIONPLAN §3.11.4` п.4); variant B — serving
 * `/rules/*` from the database — is `T_OPS.2`, to be picked up once there are
 * more than ten corpora.
 */
export function renderRule(lang: string, path: string, data: unknown): string {
  i18n.changeLanguage(lang)
  return renderToString(
    <I18nextProvider i18n={i18n}>
      <StaticRouter location={path}>
        <Routes>
          <Route
            path="/rules/:category/:direction/:country"
            element={<RulesPage initial={data as never} />}
          />
        </Routes>
      </StaticRouter>
    </I18nextProvider>,
  )
}

/**
 * The directory index. Rendered without data on purpose.
 *
 * The list is short-lived — it changes with every publication — and the page
 * fetches it on mount anyway. What prerendering buys here is the heading, the
 * lede and the shell: a crawler that follows the footer link finds a page that
 * says what this section is, rather than an empty div. The list it will index
 * on the next pass, from the corridor pages themselves, which do carry content.
 */
export function renderRulesIndex(lang: string): string {
  i18n.changeLanguage(lang)
  return renderToString(
    <I18nextProvider i18n={i18n}>
      <StaticRouter location="/rules">
        <Routes>
          <Route path="/rules" element={<RulesIndexPage />} />
        </Routes>
      </StaticRouter>
    </I18nextProvider>,
  )
}

export function render(lang: string, path = '/'): string {
  const page = PAGES[path]
  if (!page) {
    // Loud, not silent: a typo here would otherwise ship a blank page that
    // looks fine in the browser and is empty to every crawler.
    throw new Error(`entry-ssr: no prerenderable page for "${path}"`)
  }
  i18n.changeLanguage(lang)
  return renderToString(
    <I18nextProvider i18n={i18n}>
      <StaticRouter location={path}>{page()}</StaticRouter>
    </I18nextProvider>,
  )
}
