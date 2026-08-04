import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getMyTrustCircle, getUserTrustMetrics, type TrustCircles, type TrustMetrics } from '../api/trust'
import { useAuthStore } from '../stores/auth'
import MonoText from './MonoText'

export default function TrustCirclesSection() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [circles, setCircles] = useState<TrustCircles | null>(null)
  const [metrics, setMetrics] = useState<TrustMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [depth, setDepth] = useState(3)

  useEffect(() => {
    if (!user) return
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const [c, m] = await Promise.all([
          getMyTrustCircle({ depth }),
          getUserTrustMetrics(user.id),
        ])
        if (cancelled) return
        setCircles(c.data)
        setMetrics(m.data)
      } catch {
        // silent
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [user?.id, depth])

  if (!user) return null

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display font-semibold text-base text-navy">
          {t('trust.sectionTitle')}
        </h2>
        <div className="flex items-center gap-1 text-xs font-body text-muted">
          <span>{t('trust.depth')}</span>
          {[1, 2, 3, 4, 5, 6].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDepth(d)}
              className={`w-6 h-6 rounded ${
                d === depth
                  ? 'bg-cyan text-white'
                  : 'text-muted hover:text-navy hover:bg-ivory'
              }`}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs font-body text-muted">{t('trust.sectionHint')}</p>

      {loading ? (
        <MonoText className="text-xs text-muted">{t('common.loading')}</MonoText>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="bg-ivory rounded-field py-3">
              <MonoText className="text-lg text-navy font-medium">
                {metrics?.verifications_issued_count ?? 0}
              </MonoText>
              <p className="text-xs font-body text-muted">
                {t('trust.verificationsIssued')}
              </p>
            </div>
            <div className="bg-ivory rounded-field py-3">
              <MonoText className="text-lg text-navy font-medium">
                {metrics?.verifications_received_count ?? 0}
              </MonoText>
              <p className="text-xs font-body text-muted">
                {t('trust.verificationsReceived')}
              </p>
            </div>
            <div className="bg-ivory rounded-field py-3">
              <MonoText className="text-lg text-navy font-medium">
                {metrics?.dealt_with_count ?? 0}
              </MonoText>
              <p className="text-xs font-body text-muted">
                {t('trust.dealtWith')}
              </p>
            </div>
          </div>

          <div className="space-y-2 pt-2 border-t border-navy/5">
            <p className="text-xs font-display font-semibold text-muted uppercase tracking-wide">
              {t('trust.circlesTitle', { total: circles?.total_reachable ?? 0 })}
            </p>
            {circles && Object.keys(circles.circles).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(circles.circles)
                  .sort(([a], [b]) => Number(a) - Number(b))
                  .map(([level, users]) => (
                    <div
                      key={level}
                      className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-6 h-6 rounded-full bg-cyan/20 text-link text-xs font-mono flex items-center justify-center">
                          {level}
                        </span>
                        <p className="text-sm font-body text-navy">
                          {t('trust.hopLabel', { count: users.length })}
                        </p>
                      </div>
                      <MonoText className="text-xs text-muted">
                        {users.length}
                      </MonoText>
                    </div>
                  ))}
              </div>
            ) : (
              <p className="text-sm font-body text-muted py-4 text-center">
                {t('trust.empty')}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
