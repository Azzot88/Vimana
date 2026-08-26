import type { ReactElement } from 'react'
import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom/server'
import { I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import LandingPage from './pages/LandingPage'
import CarrierLandingPage from './pages/CarrierLandingPage'
import SenderLandingPage from './pages/SenderLandingPage'
import BusinessLandingPage from './pages/BusinessLandingPage'

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
