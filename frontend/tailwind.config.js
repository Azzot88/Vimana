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
        // Reads beautifully on navy. As *text on paper* it is 2.43:1, which is
        // why `link` exists below — the accent and the readable version of the
        // accent are two different values, and pretending otherwise is how the
        // contrast debt happened in the first place.
        cyan: { DEFAULT: '#58B0D9' },
        // T_TEST.8 — secondary text is a colour, not an opacity.
        //
        // Muted text used to be `text-navy/40…/60`, and the whole ramp sat under
        // WCAG AA on light surfaces: /40 is 2.57:1, /50 is 3.43:1, /20 is
        // 1.52:1, against the 4.5:1 that DESIGNGUIDELINES promises. An opacity
        // ramp invites this — every step looks like a design choice and none of
        // them carries a number, so the palette drifts below the line one
        // component at a time. Same reasoning that made `danger` a token.
        //
        // `#545C67` is navy at 70% over white, frozen as a solid so it renders
        // identically on white and on ivory: 6.79:1 and 6.12:1. Both pass with
        // room, which matters because the *next* value someone picks will be
        // relative to this one.
        muted: { DEFAULT: '#545C67' },
        // Cyan darkened until it passes on both light surfaces: 5.37:1 on white,
        // 4.84:1 on ivory. Not the 4.72:1 candidate — that one fails on ivory
        // (4.26:1), and "passes on the background I happened to test" is exactly
        // the bug being fixed here.
        link: { DEFAULT: '#1A7299' },
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
