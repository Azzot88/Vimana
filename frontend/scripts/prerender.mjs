import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

/**
 * T_UX.7 pt.2 — write the app shell with a page already rendered into `#root`.
 * T_UX.23 — four public pages instead of one.
 *
 * Runs after both browser builds and after the SSR build. Reads the finished
 * `dist/index.html` (so it picks up whatever hashed asset names Vite just
 * produced) and injects the server-rendered markup into the empty root div.
 *
 * **Separate files, not `index.html` overwritten.** If landing markup went into
 * `index.html`, every other route would ship it too and a visitor opening
 * `/login` would see a landing flash past before hydration replaced it. nginx
 * serves each file at its exact address; everything else keeps the empty shell.
 *
 * The path list comes from `entry-ssr` rather than being repeated here: a page
 * added to the router and forgotten in the build script is invisible until
 * somebody checks a crawler, which is to say never.
 *
 * Russian only, deliberately. `<html lang="ru">` and the primary corridor are
 * Russian-facing, and per-locale prerendering needs content negotiation in
 * nginx to be worth anything. Other locales still work — they hydrate and
 * switch client-side, exactly as they did before. Stated here rather than left
 * to be discovered.
 */
const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(here, '..', 'dist')
const shellPath = resolve(dist, 'index.html')
const ssrEntry = resolve(dist, 'ssr', 'entry-ssr.js')

if (!existsSync(shellPath)) {
  throw new Error(`prerender: ${shellPath} is missing — run the app build first`)
}
if (!existsSync(ssrEntry)) {
  throw new Error(`prerender: ${ssrEntry} is missing — run \`vite build --ssr\` first`)
}

const { render, PRERENDER_PATHS } = await import(pathToFileURL(ssrEntry).href)

const shell = readFileSync(shellPath, 'utf8')
const marker = '<div id="root"></div>'
if (!shell.includes(marker)) {
  // Fail loudly. A silent no-op here would ship an empty landing that looks
  // fine in the browser and is blank to every crawler — the exact failure this
  // script exists to prevent, made invisible.
  throw new Error(`prerender: could not find ${marker} in index.html`)
}

/** `/` keeps the name `landing.html` it has had since T_UX.7: nginx, the
 *  Dockerfile and anybody debugging a deploy all know it by that name, and
 *  renaming it to `index-root.html` would buy tidiness at the price of a
 *  silent 404 on the busiest address. */
const fileFor = (path) => (path === '/' ? 'landing.html' : `${path.replace(/^\//, '')}.html`)

for (const path of PRERENDER_PATHS) {
  const html = render('ru', path)
  const outPath = resolve(dist, fileFor(path))
  writeFileSync(outPath, shell.replace(marker, `<div id="root">${html}</div>`), 'utf8')
  console.log(`prerender: ${path} → ${outPath} (${html.length} chars of markup)`)
}

/**
 * T3.11.03 — the rules directory, one file per published corridor.
 *
 * Unlike the four pages above, these paths are not a list in the source: they
 * are whatever is published in the database when the build runs. So the script
 * asks the API — and **carries on without them when it cannot**.
 *
 * That fallback is not laziness. The build runs in two places: on the server,
 * inside compose, where `backend` answers; and on a developer's laptop, where
 * it does not. Failing the whole build because a laptop has no database would
 * make the common case hostage to the rare one, and the pages still work
 * without a file — nginx falls back to the SPA shell, so a person sees the
 * page and only a crawler misses it.
 *
 * Which is exactly the limitation of variant A, chosen deliberately
 * (`IMPLEMENTATIONPLAN §3.11.4` п.4). Variant B — serving `/rules/*` from the
 * database — is `T_OPS.2`, due once there are more than ten corpora.
 */
const apiBase = (process.env.PRERENDER_API_BASE || 'http://backend:8000').replace(/\/$/, '')
const ruleFileFor = (path) =>
  `rules-${path.replace(/^\/rules\//, '').replace(/\/$/, '').replace(/\//g, '-')}.html`

async function fetchJson(url) {
  const res = await fetch(url, { signal: AbortSignal.timeout(4000) })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

const { renderRule, renderRulesIndex } = await import(pathToFileURL(ssrEntry).href)

// Fetched before the index is rendered, because the index is the only page
// linking to the corridors: rendering it empty left the corridor pages
// reachable only by typing their addresses.
//
// The fetch is its own try. The index file must be written either way — with
// the catalogue when the API answered, with the heading and lede when it did
// not — because a build on a laptop with no database should still leave a page
// at `/rules` rather than fall through to the SPA shell.
let index = null
try {
  index = await fetchJson(`${apiBase}/api/rules?locale=ru`)
} catch (err) {
  console.log(
    `prerender: API at ${apiBase} not reachable (${err.message}). ` +
      'Writing the directory shell without its catalogue; corridor pages are ' +
      'skipped and render client-side, so only crawlers miss them until the ' +
      'next build on the server.',
  )
}

const indexHtml = renderRulesIndex('ru', index ?? undefined)
writeFileSync(
  resolve(dist, 'rules-index.html'),
  shell.replace(marker, `<div id="root">${indexHtml}</div>`),
  'utf8',
)
console.log(
  `prerender: /rules → ${resolve(dist, 'rules-index.html')} ` +
    `(${indexHtml.length} chars of markup, ${index ? index.length : 0} corridors)`,
)

try {
  if (index && index.length === 0) {
    console.log('prerender: no published rule sets, no corridor pages to write')
  }
  for (const entry of index ?? []) {
    // The locale of the file is Russian, like every other prerendered page:
    // `<html lang="ru">` and the founding corridor are Russian-facing. Other
    // locales hydrate and switch client-side, as they already do.
    const data = await fetchJson(
      `${apiBase}/api/rules/${entry.category_key}/${entry.direction}/${entry.jurisdiction_code}?locale=ru`,
    )
    const html = renderRule('ru', entry.path, data)
    const outPath = resolve(dist, ruleFileFor(entry.path))
    writeFileSync(outPath, shell.replace(marker, `<div id="root">${html}</div>`), 'utf8')
    console.log(`prerender: ${entry.path} → ${outPath} (${html.length} chars of markup)`)
  }
} catch (err) {
  // One line, and it says which half is missing. Silence here would look like
  // "there are no rules yet" on a build that simply could not ask.
  console.log(
    `prerender: stopped partway through the corridor pages (${err.message}). ` +
      'Pages still render client-side; only crawlers miss them until the next build.',
  )
}
