import { useTranslation } from 'react-i18next'
import type { DealStatus } from '../api/deals'

const statusClass: Record<DealStatus, string> = {
  draft:      'bg-navy/5 text-navy/60',
  matched:    'bg-navy/5 text-navy/60',
  accepted:   'bg-cyan/10 text-cyan border border-cyan/30',
  in_transit: 'bg-amber/10 text-amber border border-amber/30',
  // T3.11.17 — in the post, not yet received. Its own colour because it is its
  // own leg: the carrier is done and the parcel is still travelling.
  posted:     'bg-cyan/10 text-cyan border border-cyan/30',
  delivered:  'bg-success/10 text-success',
  confirmed:  'bg-success/10 text-success',
  closed:     'bg-navy/10 text-navy',
  // T3.11.27 — grey like 'closed' and never red: calling a deal off is an
  // outcome, not a failure, and danger colour would tell the two people who
  // agreed to it that they did something wrong.
  cancelled:  'bg-navy/10 text-navy/50',
  disputed:   'bg-amber/10 text-amber',
}

export default function StatusBadge({ status }: { status: DealStatus }) {
  const { t } = useTranslation()
  const cls = statusClass[status] ?? 'bg-navy/5 text-navy/60'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-medium ${cls}`}>
      {t(`deals.status.${status}`, { defaultValue: status })}
    </span>
  )
}
