import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/**
 * T_UX.40 — the one header every screen inside the app shell opens with.
 *
 * DESIGNGUIDELINES §9a: a third copy becomes a component. The title block was
 * written by hand on twenty screens and had drifted into five sizes and two
 * weights, so pages read as if from different products. The classes below are
 * the ones most screens already used — nothing new was designed here, the
 * majority was adopted.
 *
 * - `back` — the way out of a nested screen, above the title.
 * - `eyebrow` — the section a page belongs to (the profile's sub-pages).
 * - `description` — §9b: what this screen is for, one line under the title.
 * - `aside` — controls or counts that belong to the whole page, on the right.
 *
 * Spacing around it is the page's `space-y-*`; the shell owns the gutters
 * (`Layout`), so this adds none of its own.
 */
export default function PageHeader({
  title,
  description,
  back,
  eyebrow,
  aside,
}: {
  title: ReactNode
  description?: ReactNode
  back?: { to: string; label: ReactNode }
  eyebrow?: ReactNode
  aside?: ReactNode
}) {
  return (
    <header className="space-y-1">
      {back && (
        <Link
          to={back.to}
          className="inline-block text-xs font-body text-navy/40 transition-colors hover:text-navy"
        >
          ← {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {eyebrow && (
            <p className="text-xs font-display font-semibold uppercase tracking-wide text-navy/50">
              {eyebrow}
            </p>
          )}
          <h1 className="font-display text-2xl font-bold text-navy text-balance">{title}</h1>
          {description && (
            <div className="mt-1 max-w-[65ch] text-sm font-body text-navy/60">{description}</div>
          )}
        </div>
        {aside && <div className="flex flex-wrap items-center gap-2">{aside}</div>}
      </div>
    </header>
  )
}
