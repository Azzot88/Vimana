import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'

/**
 * T_UX.7 pt.2 — entry motion, and nothing else.
 *
 * `MOTION_INTENSITY: 3`. The landing is written to read as a document, and a
 * document that moves while you read it stops being one. So: a short rise on
 * first appearance, once, and no scroll-linked parallax, no loops, no
 * hover-scale on anything carrying information.
 *
 * Three guards, each for a different failure:
 *
 * - **`useReducedMotion`** — the system setting, honoured here as well as in the
 *   global CSS rule. The CSS `!important` kills durations but not the initial
 *   offset, so without this branch a reduced-motion user would get content
 *   jumping 12px into place with no transition: worse than either option.
 * - **`typeof window === 'undefined'`** — the prerender runs in Node. The
 *   prerendered HTML has to contain the finished page, not its first frame;
 *   `whileInView` needs an IntersectionObserver, so the server would otherwise
 *   serialise every section at `opacity: 0` and anyone with JavaScript off
 *   would get a blank page.
 * - **`hydrated`** — the first *client* render must match the server byte for
 *   byte, or React logs a hydration mismatch for every section. Motion starts
 *   one effect later. That is invisible in practice because everything wrapped
 *   here is below the fold; the hero deliberately does not use this component,
 *   since content that is already on screen must not fade in after arriving.
 */
export default function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode
  delay?: number
  className?: string
}) {
  const reduced = useReducedMotion()
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => setHydrated(true), [])

  if (reduced || !hydrated || typeof window === 'undefined') {
    return <div className={className}>{children}</div>
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-64px' }}
      transition={{ duration: 0.4, delay, ease: [0.22, 0.61, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}
