import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { corridorForTrip, type CorridorForTrip } from '../api/checklist'
import { usePrefs } from '../hooks/usePrefs'

/** T3.11.07 — «перевозчик видит требования и объявляет, что берёт такой груз».
 *
 *  The whole corpus was written for this moment and until now had no reader but
 *  the directory. A carrier ticking «животные» is agreeing to carry something a
 *  border has opinions about, and the honest place to say what those are is the
 *  screen where they tick it — not a page they would have to know to visit.
 *
 *  **It never refuses anything.** `D-COMPLIANCE-STANCE`: the platform records
 *  that you were told; it does not rule on your paperwork. So this is a list and
 *  a red line, never a disabled button.
 *
 *  **Silence and «nothing required» are different statements.** An uncovered
 *  corridor renders nothing at all rather than «всё в порядке» — printing the
 *  second where the first is true would be the platform vouching for rules it
 *  has never read.
 *
 *  Functions (PROJECT §6.2a):
 *  - `CorridorRequirements({ origin, destination, category, departAt })` —
 *    default export. Called by: `pages/NewTripPage`.
 */
interface Props {
  /** IATA codes, as a trip carries them. */
  origin: string
  destination: string
  category: string
  /** `YYYY-MM-DD` or a full ISO timestamp; only the date is used. Empty means
   *  no countdown — the list still stands, it just has no deadlines. */
  departAt?: string
}

export default function CorridorRequirements({
  origin,
  destination,
  category,
  departAt,
}: Props) {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [data, setData] = useState<CorridorForTrip | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!origin || !destination || !category) {
      setData(null)
      return
    }
    let cancelled = false
    corridorForTrip({
      origin,
      destination,
      category,
      ...(departAt ? { depart_at: departAt.slice(0, 10) } : {}),
    })
      .then(({ data: body }) => {
        if (!cancelled) setData(body)
      })
      // Silently: this is an extra panel on somebody else's screen, and an
      // error banner about a panel that failed to load is worse than no panel.
      .catch(() => {
        if (!cancelled) setData(null)
      })
    return () => {
      cancelled = true
    }
  }, [origin, destination, category, departAt])

  if (!data || !data.covered || data.items.length === 0) return null

  const mandatory = data.items.filter((i) => i.is_mandatory).length

  return (
    <div className="rounded-field border border-navy/10 bg-white px-3 py-2 space-y-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 text-left"
      >
        <span className="text-xs font-body text-navy/70">
          {t('corridor.summary', {
            category: t(`categories.${category}`, { defaultValue: category }),
            corridor: data.corridor.join(' → '),
            count: mandatory,
          })}
        </span>
        <span aria-hidden className="text-xs text-navy/30">
          {open ? '▲' : '▼'}
        </span>
      </button>

      {/* The red line stays outside the fold: a warning somebody has to expand
          to see is a warning for the people who already suspected. */}
      {data.too_late > 0 && (
        <p className="text-xs font-body text-danger font-medium">
          {data.worst_title && data.worst_days
            ? t('checklist.warnNamed', {
                title: data.worst_title,
                count: data.worst_days,
              })
            : t('checklist.warnCount', { count: data.too_late })}
        </p>
      )}

      {open && (
        <ul className="space-y-1 pt-1 border-t border-navy/5">
          {data.items.map((item) => (
            <li
              key={`${item.jurisdiction_code}-${item.code}`}
              className="flex items-baseline justify-between gap-3 flex-wrap"
            >
              <span className="text-xs font-body text-navy/70">
                {item.title}
                {item.undecided && (
                  <span className="ml-1 text-amber">
                    {t('checklist.undecided')}
                  </span>
                )}
              </span>
              <span className="text-[11px] font-mono text-navy/40">
                {item.jurisdiction_code}
                {item.lead_time_days != null &&
                  ` · ${t('checklist.leadTime', { count: item.lead_time_days })}`}
                {item.start_by && ` · ${prefs.date(item.start_by)}`}
              </span>
            </li>
          ))}
        </ul>
      )}

      {/* §9.1 — what this is and what it is not, once, under the list. */}
      <p className="text-[11px] font-body text-navy/40">
        {t('corridor.notBlocking')}{' '}
        <Link
          to={`/checklist?category=${encodeURIComponent(category)}`}
          className="text-cyan hover:underline"
        >
          {t('checklist.warnSeeList')}
        </Link>
      </p>
    </div>
  )
}
