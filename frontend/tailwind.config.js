/**
 * T_UX.7 pt.1 — the single source of design tokens.
 *
 * Before this, the brand existed four times: these tokens, a 576-line CSS
 * string inside `LandingPage.tsx` with its own navy and its own three accents,
 * and two static landings with two more palettes (one of them serif). Someone
 * arriving from a landing page walked into a different product.
 *
 * Rules that hold this together:
 *
 * - **One accent that means "act", one that means "attention", one that means
 *   "stop".** `cyan` is progress and interaction, `amber` is runway lights (look
 *   here), `danger` is only for the irreversible. A fourth accent has to earn
 *   its place by naming a state the other three cannot.
 * - **`danger` is a token, not `red-600`.** It was used raw in 19 places, which
 *   is how a palette drifts: a raw hex has no rule attached, so nobody knows
 *   whether the next red should match it.
 * - **One radius system.** `card` for containers, `field` for the controls
 *   inside them. Varying radius per element is the classic tell; one system
 *   with two steps reads as intent.
 * - **Shadows carry the background hue.** Pure-black shadow on an ivory page is
 *   the reason flat UIs look dirty rather than lit.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Deep steel-blue, not black: the terminal at night, not a void.
        navy: {
          DEFAULT: '#0A1626',
          mid: '#16304F',
          soft: '#1C3252',
        },
        // Sky. Progress, active state, anything the user is doing right now.
        cyan: { DEFAULT: '#58B0D9' },
        // Runway lights. "Pay attention", never "danger" — that distinction is
        // the whole reason both exist.
        amber: { DEFAULT: '#FF7A2F' },
        // Boarding-pass paper.
        ivory: { DEFAULT: '#F5F3EE' },
        // Reserved for the irreversible and the failed. Never for overdue,
        // never for debt, never for emphasis (DESIGNGUIDELINES).
        danger: { DEFAULT: '#DC2626' },
        success: { DEFAULT: '#16A34A' },
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
        // Departure board: codes, amounts, dates, keys, anything compared by eye.
        mono: ['IBM Plex Mono', 'monospace'],
      },
      borderRadius: {
        card: '1rem',
        field: '0.5rem',
      },
      boxShadow: {
        // Tinted with the navy the page is built on, so elevation reads as
        // light falling on paper rather than as a grey smudge.
        card: '0 1px 2px rgba(10,22,38,0.04), 0 8px 24px -12px rgba(10,22,38,0.12)',
        lift: '0 2px 4px rgba(10,22,38,0.06), 0 16px 40px -16px rgba(10,22,38,0.18)',
      },
      zIndex: {
        // A named scale instead of the 9999 that appears once and then twice.
        nav: '100',
        overlay: '200',
        modal: '300',
        toast: '400',
      },
    },
  },
  plugins: [],
}
