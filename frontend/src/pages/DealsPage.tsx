import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { listDeals, type Deal } from '../api/deals'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'

export default function DealsPage() {
  const user = useAuthStore((s) => s.user)
  const [deals, setDeals] = useState<Deal[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listDeals()
      .then((r) => setDeals(r.data))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">Загрузка...</MonoText>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">Сделки</h1>
      {deals.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm font-body text-navy/40">Нет сделок</p>
          <Link to="/trips" className="inline-block mt-3 text-sm text-cyan hover:underline font-body">
            Найти рейс
          </Link>
        </div>
      ) : (
        <div className="grid gap-3">
          {deals.map((deal) => {
            const role = deal.carrier_id === user?.id ? 'Перевозчик' : 'Отправитель'
            return (
              <Link
                key={deal.id}
                to={`/deals/${deal.id}`}
                className="bg-white rounded-xl border border-navy/10 p-5 hover:border-cyan/40 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="space-y-1.5">
                    <MonoText className="text-base text-navy font-medium">
                      {deal.origin} → {deal.destination}
                    </MonoText>
                    <div className="flex items-center gap-3 text-xs font-body text-navy/50">
                      <span className="bg-navy/5 px-2 py-0.5 rounded font-mono">{role}</span>
                      <span>{deal.cargo_description}</span>
                      <MonoText className="text-xs">{deal.cargo_weight} кг</MonoText>
                    </div>
                    <MonoText className="text-xs text-navy/40">
                      {new Date(deal.depart_at).toLocaleString('ru-RU')}
                    </MonoText>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <StatusBadge status={deal.status} />
                    <MonoText className="text-xs text-navy/30">{deal.id.slice(0, 8)}...</MonoText>
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
