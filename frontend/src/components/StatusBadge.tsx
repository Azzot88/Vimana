import { useTranslation } from 'react-i18next'
import type { DealStatus } from '../api/deals'

const statusClass: Record<DealStatus, string> = {
  draft:      'bg-gray-100 text-gray-600',
  matched:    'bg-gray-100 text-gray-600',
  accepted:   'bg-cyan/10 text-cyan border border-cyan/30',
  in_transit: 'bg-amber/10 text-amber border border-amber/30',
  delivered:  'bg-green-100 text-green-700',
  confirmed:  'bg-green-100 text-green-700',
  closed:     'bg-navy/10 text-navy',
  disputed:   'bg-orange-100 text-orange-600',
}

export default function StatusBadge({ status }: { status: DealStatus }) {
  const { t } = useTranslation()
  const cls = statusClass[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-medium ${cls}`}>
      {t(`deals.status.${status}`, { defaultValue: status })}
    </span>
  )
}
