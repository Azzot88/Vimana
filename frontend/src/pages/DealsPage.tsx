import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { listDeals, type Deal } from '../api/deals'
import StatusBadge from '../components/StatusBadge'
import MonoText from '../components/MonoText'

export default function DealsPage() {
  const user = useAuthStore((s) => s.user)
  const { t, i18n } = useTranslation()
  const [deals, setDeals] = useState<Deal[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listDeals()
      .then((r) => setDeals(r.data.items))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <MonoText className="text-navy/40 text-sm">{t('common.loading')}</MonoText>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">{t('deals.title')}</h1>
      {deals.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm font-body text-navy/40">{t('deals.noDeals')}</p>
          <Link to="/trips" className="inline-block mt-3 text-sm text-cyan hover:underline font-body">
            {t('dashboard.findTrip')}
          </Link>
        </div>
      ) : (
        <div className="grid gap-3">
          {deals.map((deal) => {
            const role = deal.carrier_id === user?.id ? t('dashboard.carrier') : t('dashboard.sender')
            return (
              <Link
                key={deal.id}
                to={`/deals/${deal.id}`}
                className="bg-white rounded-card border border-navy/10 p-5 hover:border-cyan/40 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="space-y-1.5">
                    <MonoText className="text-base text-navy font-medium">
                      {deal.id.slice(0, 8)}...
                    </MonoText>
                    <div className="flex items-center gap-3 text-xs font-body text-navy/50">
                      <span className="bg-navy/5 px-2 py-0.5 rounded font-mono">{role}</span>
                    </div>
                    <MonoText className="text-xs text-navy/40">
                      {new Date(deal.created_at).toLocaleString(i18n.language)}
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
