import React from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import App from './App'
import './i18n'
import './index.css'

const root = document.getElementById('root')!

/**
 * T_UX.7 pt.2 — hydrate the prerendered landing, mount everything else.
 *
 * `dist/landing.html` ships with the landing already rendered inside `#root`
 * (see `scripts/prerender.mjs`); `index.html`, served for every other route,
 * ships an empty one. `createRoot` over prerendered markup throws that markup
 * away and re-renders from scratch — a visible flash, and the whole point of
 * prerendering wasted. The choice is made from what is actually in the DOM
 * rather than from a build flag that could disagree with it.
 */
const app = (
  <React.StrictMode>
    <App />
  </React.StrictMode>
)

if (root.hasChildNodes()) {
  hydrateRoot(root, app)
} else {
  createRoot(root).render(app)
}
