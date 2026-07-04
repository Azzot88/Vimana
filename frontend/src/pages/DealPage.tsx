import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { getDeal, acceptDeal, addEvent, confirmDeal, type DealDetail } from '../api/deals'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'

export default function DealPage() {
  const { dealId } = useParams<{ dealId: string }>()
  const user = useAuthStore((s) => s.user)
  const [deal, setDeal] = useState<DealDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    if (!dealId) return
    try {
      const { data } = await getDeal(dealId)
      setDeal(data)
    } catch {
      setError('Сделка не найдена')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [dealId])

  const handleAction = async (action: 'accept' | 'handoff' | 'confirm') => {
    if (!dealId) return
    setActionLoading(true)
    setError('')
    try {
      if (action === 'accept') {
        const { data } = await acceptDeal(dealId)
        setDeal(data)
      } else if (action === 'handoff') {
        await addEvent(dealId, 'handoff', 'Груз передан перевозчику')
        await load()
      } else if (action === 'confirm') {
        const { data } = await confirmDeal(dealId)
        setDeal(data)
      }
    } catch {
      setError('Действие не выполнено')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">Загрузка...</MonoText>
      </div>
    )
  }

  if (!deal) {
    return (
      <div className="text-center py-24">
        <p className="text-sm font-body text-navy/40">{error || 'Сделка не найдена'}</p>
      </div>
    )
  }

  const isCarrier = deal.carrier_id === user?.id
  const isSender = deal.sender_id === user?.id

  return (
    <div className="max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/deals" className="text-xs font-body text-navy/40 hover:text-navy transition-colors">
          ← Сделки
        </Link>
      </div>

      <div className="bg-white rounded-xl border border-navy/10 overflow-hidden">
        <div className="bg-navy px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div className="space-y-1">
              <p className="text-xs font-mono text-white/40 uppercase tracking-widest">Посадочный талон</p>
              <MonoText className="text-xl text-white font-medium">
                {deal.origin} → {deal.destination}
              </MonoText>
              <MonoText className="text-sm text-white/60">
                {new Date(deal.depart_at).toLocaleString('ru-RU')}
              </MonoText>
            </div>
            <div className="self-start"><StatusBadge status={deal.status} /></div>
          </div>
        </div>

        <div className="p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Отправитель</p>
            <p className="text-sm font-body text-navy font-medium">{deal.sender_name}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Перевозчик</p>
            <p className="text-sm font-body text-navy font-medium">{deal.carrier_name}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Груз</p>
            <p className="text-sm font-body text-navy">{deal.cargo_description}</p>
          </div>
          <div>
            <p className="text-xs font-body font-medium text-navy/40 mb-1">Категория</p>
            <MonoText className="text-sm text-navy">{deal.cargo_category}</MonoText>
          </div>
          <div className="sm:col-span-2">
            <p className="text-xs font-body font-medium text-navy/40 mb-1">ID сделки</p>
            <MonoText className="text-xs text-navy/50 break-all">{deal.id}</MonoText>
          </div>
        </div>

        {error && (
          <div className="px-4 sm:px-6 pb-4">
            <p className="text-xs font-mono text-orange-600">{error}</p>
          </div>
        )}

        <div className="px-4 sm:px-6 pb-6 flex flex-col sm:flex-row sm:flex-wrap gap-3">
          {isCarrier && deal.status === 'matched' && (
            <button
              onClick={() => handleAction('accept')}
              disabled={actionLoading}
              className="bg-cyan text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : 'Принять сделку'}
            </button>
          )}
          {isCarrier && deal.status === 'accepted' && (
            <button
              onClick={() => handleAction('handoff')}
              disabled={actionLoading}
              className="bg-amber text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : 'Зафиксировать передачу'}
            </button>
          )}
          {isSender && deal.status === 'delivered' && (
            <button
              onClick={() => handleAction('confirm')}
              disabled={actionLoading}
              className="bg-green-600 text-white font-display font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {actionLoading ? '...' : 'Подтвердить получение'}
            </button>
          )}
          <Link
            to={`/deals/${deal.id}/vault`}
            className="border border-navy/20 text-navy font-body font-medium px-5 py-3 min-h-[2.75rem] rounded-lg text-sm hover:border-cyan transition-colors text-center"
          >
            DealVault →
          </Link>
        </div>
      </div>
    </div>
  )
}
