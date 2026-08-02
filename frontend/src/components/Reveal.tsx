import { motion, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'

/**
 * T_UX.7 pt.2 — entry motion, and nothing else.
 *
 * `MOTION_INTENSITY: 3`. The landing is written to read as a document, and a
 * document that moves while you read it stops being one. So: a short rise on
 * first appearance, once, and no scroll-linked parallax, no loops, no
 * hover-scale on anything that carries information.
 *
 * `useReducedMotion` is checked here as well as in the global CSS rule, because
 * the CSS `!important` override kills *durations* but not the initial offset —
 * without this branch a reduced-motion user would see content jump from 12px
 * down to place with no transition, which is worse than either option.
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
  if (reduced) return <div className={className}>{children}</div>

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
