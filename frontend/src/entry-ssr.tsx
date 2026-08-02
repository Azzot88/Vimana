import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router-dom/server'
import { I18nextProvider } from 'react-i18next'
import i18n from './i18n'
import LandingPage from './pages/LandingPage'

/**
 * T_UX.7 pt.2 — the landing, rendered to HTML at build time.
 *
 * Only the landing. The rest of the product is behind a session and has nothing
 * to prerender: an empty dashboard shell in the HTML would help no crawler and
 * would have to be kept in sync with the real one forever.
 *
 * `StaticRouter` rather than `BrowserRouter` because there is no history in
 * Node, and the location is fixed at `/` — this output is only ever served
 * there (see `nginx/default.conf`).
 *
 * The result is written into `dist/landing.html` by `scripts/prerender.mjs` and
 * hydrated by the ordinary app bundle, so the page a crawler reads and the page
 * a person interacts with are produced by the same component. That is the whole
 * reason for doing it this way instead of hand-writing a static twin, which is
 * exactly how the brand ended up existing four times to begin with.
 */
export function render(lang: string): string {
  i18n.changeLanguage(lang)
  return renderToString(
    <I18nextProvider i18n={i18n}>
      <StaticRouter location="/">
        <LandingPage />
      </StaticRouter>
    </I18nextProvider>,
  )
}
