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
import { RULES_DATA_ID } from './api/rulesPublic'

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
 * **Two callers now, and that is the point** (`T_OPS.2`). The build-time step
 * still writes a file per corridor, and `scripts/ssr-server.mjs` calls the same
 * function per request from the live database. The files stopped being the
 * delivery mechanism and became the fallback for a renderer that is down; the
 * markup is identical either way, because it is the same function.
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
 * The directory index, rendered from the same data the page would fetch.
 *
 * It used to render empty, on the argument that the list changes with every
 * publication and the page fetches it on mount anyway. That was wrong in one
 * specific way: the index is the **only** thing linking to the corridor pages,
 * so a crawler following the footer link found a page with no outbound links
 * and the corridors stayed unreachable except by guessing their addresses. The
 * list being short-lived is an argument for rebuilding often, not for shipping
 * it blank.
 *
 * `data` is optional so the build still produces a usable page when the API is
 * unreachable — the shell, the heading and the lede, which is what it produced
 * before. `scripts/prerender.mjs` passes the index it already fetched.
 */
export function renderRulesIndex(lang: string, data?: unknown): string {
  i18n.changeLanguage(lang)
  return renderToString(
    <I18nextProvider i18n={i18n}>
      <StaticRouter location="/rules">
        <Routes>
          <Route path="/rules" element={<RulesIndexPage initial={data as never} />} />
        </Routes>
      </StaticRouter>
    </I18nextProvider>,
  )
}

/** Typed as a record so indexing it with a string is not an implicit `any`. */
const ATTR_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

/**
 * Put rendered markup into the shell, and the data it was rendered from
 * beside it (`T_OPS.2`).
 *
 * Both callers used to do the `String.replace` themselves, which was fine
 * while there was nothing to carry but markup. Now the payload has to travel
 * too: a page hydrating against content while its component starts empty makes
 * React discard the server's work and paint a skeleton over a finished page.
 *
 * `<` is escaped because `</script>` inside a JSON string closes the tag no
 * matter what `type` says. The address is stamped alongside so the browser can
 * tell whether the payload belongs to the page it is currently on.
 */
export function injectPage(
  shell: string,
  markup: string,
  data?: unknown,
  path?: string,
): string {
  const marker = '<div id="root"></div>'
  if (!shell.includes(marker)) {
    throw new Error(`injectPage: could not find ${marker} in the shell`)
  }
  if (data !== undefined && !path) {
    // The address is what makes the payload usable: the document outlives
    // client-side navigation, and an untagged payload would be handed to
    // whatever page mounts next.
    throw new Error('injectPage: data was given without the path it belongs to')
  }
  // Escaped because the path comes from the request line: nginx routes
  // `/rules/<a>/<b>/<c>` with `[^/]+` for each segment, and a double quote is
  // a perfectly legal character there. Unescaped it would close the attribute
  // and put whatever followed into the tag.
  const safePath = String(path ?? '').replace(/[&<>"']/g, (c) => ATTR_ESCAPES[c])
  const payload =
    data === undefined
      ? ''
      : `<script id="${RULES_DATA_ID}" type="application/json" data-path="${safePath}">` +
        `${JSON.stringify(data).replace(/</g, '\\u003c')}</script>`
  return shell.replace(marker, `<div id="root">${markup}</div>${payload}`)
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
