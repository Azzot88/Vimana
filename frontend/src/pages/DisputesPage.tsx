import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listDeals, type Deal } from '../api/deals'
import { usePrefs } from '../hooks/usePrefs'
import MonoText from '../components/MonoText'
import StatusBadge from '../components/StatusBadge'

/** T_UX.14 — open disputes, on their own screen.
 *
 *  When the deals tab became history, disputes were the one thing that could
 *  not go with it. A finished deal is worth looking up; an open dispute is
 *  waiting on somebody, sometimes for weeks, and burying it in a chronological
 *  list is how it stops being looked at. It gets a place of its own precisely
 *  because it hangs around.
 */
export default function DisputesPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [deals, setDeals] = useState<Deal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    listDeals()
      .then(({ data }) => setDeals(data.items.filter((d) => d.status === 'disputed')))
      .catch(() => setError(t('common.errorGeneric') as string))
      .finally(() => setLoading(false))
  }, [t])

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
      <h1 className="text-xl font-display font-semibold text-navy">
        {t('nav.disputes')}
      </h1>

      {error && <p className="text-sm font-body text-danger">{error}</p>}
      {loading && <p className="text-sm font-body text-navy/40">{t('common.loading')}</p>}

      {!loading && deals.length === 0 && (
        <p className="text-sm font-body text-navy/40">{t('disputes.none')}</p>
      )}

      <div className="space-y-3">
        {deals.map((deal) => (
          <Link
            key={deal.id}
            to={`/deals/${deal.id}`}
            className="block bg-white rounded-card border border-navy/10 p-4 hover:border-cyan/40 transition-colors"
          >
            <div className="flex flex-wrap items-center gap-3">
              <MonoText className="text-sm text-navy font-medium">
                {deal.id.slice(0, 8)}
              </MonoText>
              <StatusBadge status={deal.status} />
              <MonoText className="text-xs text-navy/40 ml-auto">
                {prefs.dateTime(deal.created_at)}
              </MonoText>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
