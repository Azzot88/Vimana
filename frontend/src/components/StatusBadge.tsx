import type { DealStatus } from '../api/deals'

interface StatusBadgeProps {
  status: DealStatus
}

const statusConfig: Record<DealStatus, { label: string; className: string }> = {
  draft:     { label: 'Черновик',    className: 'bg-gray-100 text-gray-600' },
  matched:   { label: 'Подобрано',   className: 'bg-gray-100 text-gray-600' },
  accepted:  { label: 'Принято',     className: 'bg-cyan/10 text-cyan border border-cyan/30' },
  in_transit:{ label: 'В пути',      className: 'bg-amber/10 text-amber border border-amber/30' },
  delivered: { label: 'Доставлено',  className: 'bg-green-100 text-green-700' },
  confirmed: { label: 'Подтверждено',className: 'bg-green-100 text-green-700' },
  closed:    { label: 'Закрыто',     className: 'bg-navy/10 text-navy' },
  disputed:  { label: 'Спор',        className: 'bg-orange-100 text-orange-600' },
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status] ?? { label: status, className: 'bg-gray-100 text-gray-600' }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded text-xs font-mono font-medium ${config.className}`}>
      {config.label}
    </span>
  )
}
