import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { getLeadWarning, type LeadWarning } from '../api/checklist'

/** T3.11.06 — the one red line, shown where the decision is being made.
 *
 *  The wizard is a page somebody goes to. This is the same fact delivered where
 *  they already are — publishing a trip, or looking at one. **31 % of this
 *  market publishes inside two days of the flight**, so a requirement with a
 *  thirty-day lead time is not an edge case: it is the third of listings for
 *  which the honest answer is «нет, не успеете».
 *
 *  **It renders nothing unless it has something to say.** No departure, an
 *  airport we cannot place, a corridor with no published corpus, or a corridor
 *  with time to spare all come back empty, and an empty warning drawn as a grey
 *  «всё в порядке» would be the platform vouching for paperwork it has not seen.
 *
 *  Functions (PROJECT §6.2a):
 *  - `LeadTimeWarning({ origin, destination, category, departAt })` — default
 *    export. Called by: `pages/NewTripPage`, `pages/TripsPage`.
 */
interface Props {
  /** IATA codes, as a trip carries them. */
  origin: string
  destination: string
  category: string
  /** `YYYY-MM-DD` or a full ISO timestamp; only the date is used. */
  departAt: string
}

export default function LeadTimeWarning({
  origin,
  destination,
  category,
  departAt,
}: Props) {
  const { t } = useTranslation()
  const [warning, setWarning] = useState<LeadWarning | null>(null)

  useEffect(() => {
    if (!origin || !destination || !category || !departAt) {
      setWarning(null)
      return
    }
    let cancelled = false
    getLeadWarning({
      origin,
      destination,
      category,
      depart_at: departAt.slice(0, 10),
    })
      .then(({ data }) => {
        if (!cancelled) setWarning(data)
      })
      // Silently: this is an extra line on somebody else's screen, and an error
      // banner about a warning that failed to load is worse than no warning.
      .catch(() => {
        if (!cancelled) setWarning(null)
      })
    return () => {
      cancelled = true
    }
  }, [origin, destination, category, departAt])

  if (!warning || warning.too_late === 0) return null

  return (
    <div className="rounded-field border border-danger/40 bg-danger/5 px-3 py-2 space-y-1">
      <p className="text-xs font-body text-danger font-medium">
        {warning.worst_title && warning.worst_days
          ? t('checklist.warnNamed', {
              title: warning.worst_title,
              count: warning.worst_days,
            })
          : t('checklist.warnCount', { count: warning.too_late })}
      </p>
      {/* Not a refusal, and the copy says so: `D-COMPLIANCE-STANCE` — the
          platform records that you were told, it does not rule on your
          paperwork. The link goes to the full list, because «что именно» is the
          next question and hunting for it is where people give up. */}
      <p className="text-[11px] font-body text-navy/50">
        {t('checklist.warnNotBlocking')}{' '}
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
