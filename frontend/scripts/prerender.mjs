import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

/**
 * T_UX.7 pt.2 — write `dist/landing.html`: the app shell with the landing
 * already rendered into `#root`.
 *
 * Runs after both browser builds and after the SSR build. Reads the finished
 * `dist/index.html` (so it picks up whatever hashed asset names Vite just
 * produced) and injects the server-rendered markup into the empty root div.
 *
 * **A separate file, not `index.html` overwritten.** If the landing markup went
 * into `index.html`, every other route would ship it too and a visitor opening
 * `/login` would see the landing flash past before hydration replaced it. nginx
 * serves this file for `/` only; everything else keeps the empty shell.
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
const outPath = resolve(dist, 'landing.html')

if (!existsSync(shellPath)) {
  throw new Error(`prerender: ${shellPath} is missing — run the app build first`)
}
if (!existsSync(ssrEntry)) {
  throw new Error(`prerender: ${ssrEntry} is missing — run \`vite build --ssr\` first`)
}

const { render } = await import(pathToFileURL(ssrEntry).href)
const html = render('ru')

const shell = readFileSync(shellPath, 'utf8')
const marker = '<div id="root"></div>'
if (!shell.includes(marker)) {
  // Fail loudly. A silent no-op here would ship an empty landing that looks
  // fine in the browser and is blank to every crawler — the exact failure this
  // script exists to prevent, made invisible.
  throw new Error(`prerender: could not find ${marker} in index.html`)
}

writeFileSync(outPath, shell.replace(marker, `<div id="root">${html}</div>`), 'utf8')
console.log(`prerender: wrote ${outPath} (${html.length} chars of markup)`)
