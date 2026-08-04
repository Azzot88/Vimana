import { useTranslation } from 'react-i18next'
import type { DealStatus } from '../api/deals'

const statusClass: Record<DealStatus, string> = {
  draft:      'bg-navy/5 text-muted',
  matched:    'bg-navy/5 text-muted',
  accepted:   'bg-cyan/10 text-link border border-cyan/30',
  in_transit: 'bg-amber/10 text-amber border border-amber/30',
  delivered:  'bg-success/10 text-success',
  confirmed:  'bg-success/10 text-success',
  closed:     'bg-navy/10 text-navy',
  disputed:   'bg-amber/10 text-amber',
}

export default function StatusBadge({ status }: { status: DealStatus }) {
  const { t } = useTranslation()
  const cls = statusClass[status] ?? 'bg-navy/5 text-muted'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-medium ${cls}`}>
      {t(`deals.status.${status}`, { defaultValue: status })}
    </span>
  )
}
