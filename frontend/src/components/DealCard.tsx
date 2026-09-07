import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { Deal } from '../api/deals'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from './MonoText'
import StatusBadge from './StatusBadge'

/** T3.11.23 — one deal, in the three things people identify it by: the number
 *  they say out loud, a name, and the price.
 *
 *  **The name is derived, not asked for** (owner's decision 2026-09-07):
 *  «Документы · DXB → JFK» is built from the category and the route the deal
 *  already carries. A name field would have been one more empty box on a market
 *  where 0.1 % of posts name a price — and every card would then read «без
 *  названия», which is worse than no field at all.
 *
 *  **The price is missing while nothing is agreed**, and that is printed as
 *  nothing rather than as zero: a deal under negotiation has no price, and a
 *  card that shows 0 makes a claim neither side made.
 *
 *  Functions (PROJECT §6.2a):
 *  - `DealCard({ deal })` — default export. Called by: `ChatPage`,
 *    `DealsByPersonPage`.
 */
export default function DealCard({ deal }: { deal: Deal }) {
  const { t } = useTranslation()
  const prefs = usePrefs()

  const category = deal.cargo_category
    ? t(`categories.${deal.cargo_category}`, { defaultValue: deal.cargo_category })
    : null
  const route =
    deal.origin && deal.destination ? `${deal.origin} → ${deal.destination}` : null
  const title = [category, route].filter(Boolean).join(' · ')

  return (
    <Link
      to={`/deals/${deal.id}/vault`}
      className="block bg-white rounded-card border border-navy/10 px-4 py-3 hover:border-cyan/40 transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-body font-medium text-navy truncate">
            {title || deal.id.slice(0, 8)}
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {/* The number is set in mono and not truncated: it exists to be read
                aloud and pasted, and a shortened one cannot do either. */}
            {deal.shipment_no && (
              <MonoText className="text-xs text-navy/60 tracking-wide">
                № {deal.shipment_no}
              </MonoText>
            )}
            {deal.price_total != null && (
              <MonoText className="text-xs text-navy">
                {deal.price_total} {deal.currency ?? prefs.currency}
              </MonoText>
            )}
            <MonoText className="text-xs text-navy/40">
              {prefs.dateTime(deal.created_at)}
            </MonoText>
          </div>
        </div>
        <StatusBadge status={deal.status} />
      </div>
    </Link>
  )
}
