import { createServer } from 'node:http'
import { readFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

/**
 * T_OPS.2 — `/rules` and `/rules/*` rendered from the database, per request.
 *
 * ## Why this exists
 *
 * Before it, those pages were written to files at build time (variant A) and a
 * rule published after the last deploy was invisible to a crawler until the
 * next one. The recorded threshold for replacing that was "more than ten
 * corpora", and it was measuring the wrong quantity: the cost is not how many
 * corridors exist, it is how often they change, and changing is what this
 * corpus is for. At four corridors the owner was already rebuilding the
 * frontend to publish a paragraph. Publishing and being visible are now one
 * event.
 *
 * ## Why a separate process rather than the backend emitting HTML
 *
 * The backend has the data and could render these pages itself, in Python. It
 * would also then own a second copy of the markup, which drifts from the React
 * one within a month and drifts silently, because nobody opens both. Here the
 * SSR bundle is the same code the browser runs; there is one page, rendered in
 * two places, and it cannot disagree with itself.
 *
 * ## What happens when something is down
 *
 * Two failures, two different answers, neither of them an error page.
 *
 * If **this process** is down, nginx catches the 502 and falls back to the
 * prerendered file, and past that to the SPA shell. That is why the prerender
 * step stays in the build: those files are no longer the delivery mechanism,
 * they are the floor.
 *
 * If **the API** is down or slow, this process returns the shell with a 200.
 * The reader gets a page that fetches its own data client-side, which is what
 * they got before any of this existed. Returning 502 here would be worse: it
 * would ask nginx to serve a file that may itself be older than the shell.
 *
 * ## Caching
 *
 * A short in-memory TTL, not because the database is slow (it is four rows) but
 * because a crawler walking every corridor should not become one query per hit
 * forever. `SSR_CACHE_TTL_MS` is deliberately small: the whole point of this
 * process is that publishing is visible immediately, and a long TTL would
 * quietly restore the problem it was built to remove.
 */
const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(here, '..', 'dist')
const shellPath = resolve(dist, 'index.html')
const ssrEntry = resolve(dist, 'ssr', 'entry-ssr.js')

const PORT = Number(process.env.SSR_PORT || 3000)
const API_BASE = (process.env.SSR_API_BASE || 'http://backend:8000').replace(/\/$/, '')
const TTL = Number(process.env.SSR_CACHE_TTL_MS || 15_000)
const API_TIMEOUT_MS = Number(process.env.SSR_API_TIMEOUT_MS || 3_000)
const LANG = process.env.SSR_LANG || 'ru'

for (const [label, path] of [['index.html', shellPath], ['ssr bundle', ssrEntry]]) {
  if (!existsSync(path)) {
    // Loud and immediate. A server that starts without its bundle would answer
    // every request with the shell and look healthy while doing nothing.
    throw new Error(`ssr-server: ${label} missing at ${path} — run the build first`)
  }
}

const shell = readFileSync(shellPath, 'utf8')

const { renderRule, renderRulesIndex, injectPage } = await import(
  pathToFileURL(ssrEntry).href
)

/** url -> { at, value }. Bounded by the number of published corridors. */
const cache = new Map()

async function fetchJson(url) {
  const cached = cache.get(url)
  if (cached && Date.now() - cached.at < TTL) return cached.value

  const res = await fetch(url, { signal: AbortSignal.timeout(API_TIMEOUT_MS) })
  if (res.status === 404) {
    const miss = { notFound: true }
    cache.set(url, { at: Date.now(), value: miss })
    return miss
  }
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  const value = await res.json()
  cache.set(url, { at: Date.now(), value })
  return value
}

/** `/rules/<category>/<direction>/<country>` with an optional trailing slash. */
const CORRIDOR = /^\/rules\/([^/]+)\/([^/]+)\/([^/]+)\/?$/

function send(res, status, body) {
  res.writeHead(status, {
    'Content-Type': 'text/html; charset=utf-8',
    // Same header the static files carried. The document names hashed asset
    // files, so a cached copy pins the browser to an older build.
    'Cache-Control': 'no-cache',
    'Content-Length': Buffer.byteLength(body),
  })
  res.end(body)
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://ssr')
  const path = url.pathname

  if (path === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'text/plain' })
    return res.end('ok\n')
  }

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { Allow: 'GET, HEAD' })
    return res.end()
  }

  try {
    if (path === '/rules' || path === '/rules/') {
      const index = await fetchJson(`${API_BASE}/api/rules?locale=${LANG}`)
      // The data travels with the markup so the browser's first render matches
      // the server's; without it hydration discards this page and repaints a
      // skeleton over it.
      return send(res, 200, injectPage(shell, renderRulesIndex(LANG, index), index, path))
    }

    const match = CORRIDOR.exec(path)
    if (match) {
      const [, category, direction, country] = match.map(decodeURIComponent)
      const data = await fetchJson(
        `${API_BASE}/api/rules/${encodeURIComponent(category)}/` +
          `${encodeURIComponent(direction)}/${encodeURIComponent(country)}?locale=${LANG}`,
      )
      if (data.notFound) {
        // The shell, with an honest 404. Rendering the page without data would
        // put its loading skeleton in the markup, and a skeleton is the one
        // thing worse than an empty root for a crawler: it looks like content.
        // The browser reaches the same 404 from the API and shows the
        // product's own "no rules for this corridor" screen.
        return send(res, 404, shell)
      }
      return send(res, 200, injectPage(shell, renderRule(LANG, path, data), data, path))
    }

    // nginx only routes the two patterns above here. Anything else is a
    // misconfiguration, and saying so beats rendering something plausible.
    return send(res, 404, shell)
  } catch (err) {
    // The API is unreachable or slow. The shell still works: the page fetches
    // its own data in the browser, which is exactly what it did before this
    // process existed. A 502 here would ask nginx for a file that may be older
    // than the shell.
    console.error(`ssr-server: ${path} falling back to the shell (${err.message})`)
    return send(res, 200, shell)
  }
})

server.listen(PORT, () => {
  console.log(
    `ssr-server: listening on :${PORT}, API ${API_BASE}, cache ${TTL}ms, lang ${LANG}`,
  )
})

for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => {
    server.close(() => process.exit(0))
  })
}
