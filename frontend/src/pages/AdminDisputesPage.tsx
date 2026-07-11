import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import {
  claimDispute,
  listDisputes,
  resolveDispute,
  type Dispute,
} from '../api/admin'
import MonoText from '../components/MonoText'

export default function AdminDisputesPage() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [disputes, setDisputes] = useState<Dispute[]>([])
  const [loading, setLoading] = useState(true)
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const [verdict, setVerdict] = useState('')
  const [closesDeal, setClosesDeal] = useState(false)
  const [error, setError] = useState('')

  const canView = user?.is_arbiter || user?.is_superuser
  if (!canView) return <Navigate to="/dashboard" replace />

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await listDisputes({ limit: 50 })
      setDisputes(data.items)
    } catch {
      setError(t('admin.loadError'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleClaim = async (id: string) => {
    setError('')
    try {
      await claimDispute(id)
      await load()
    } catch {
      setError(t('admin.claimError'))
    }
  }

  const handleResolve = async (id: string) => {
    if (!verdict.trim()) return
    setError('')
    try {
      await resolveDispute(id, verdict.trim(), closesDeal)
      setResolvingId(null)
      setVerdict('')
      setClosesDeal(false)
      await load()
    } catch {
      setError(t('admin.resolveError'))
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display font-bold text-2xl text-navy">
        {t('admin.disputesTitle')}
      </h1>

      {error && (
        <p className="text-xs font-mono text-red-600">{error}</p>
      )}

      {loading ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('common.loading')}
        </p>
      ) : disputes.length === 0 ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('admin.disputesEmpty')}
        </p>
      ) : (
        <div className="grid gap-4">
          {disputes.map((d) => {
            const mine = d.arbiter_id === user?.id
            const canClaim = d.status === 'open'
            const canResolve = d.status === 'claimed' && (mine || user?.is_superuser)
            return (
              <div
                key={d.id}
                className="bg-white rounded-xl border border-navy/10 p-4 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <MonoText className="text-xs text-navy/50 break-all">
                    #{d.id.slice(0, 8)}
                  </MonoText>
                  <span
                    className={`text-xs font-mono px-2 py-0.5 rounded ${
                      d.status === 'open'
                        ? 'bg-red-100 text-red-700'
                        : d.status === 'claimed'
                        ? 'bg-amber/20 text-amber'
                        : 'bg-navy/10 text-navy/60'
                    }`}
                  >
                    {t(`admin.status.${d.status}`)}
                  </span>
                </div>
                <p className="text-sm font-body text-navy whitespace-pre-wrap">
                  {d.reason}
                </p>
                <div className="flex flex-wrap gap-2 pt-2">
                  <Link
                    to={`/deals/${d.deal_id}`}
                    className="text-xs font-body text-cyan hover:underline"
                  >
                    {t('admin.viewDeal')} →
                  </Link>
                  {mine && (
                    <Link
                      to={`/admin/deals/${d.deal_id}/vault`}
                      className="text-xs font-body text-cyan hover:underline"
                    >
                      {t('admin.viewVault')} →
                    </Link>
                  )}
                  {canClaim && (
                    <button
                      onClick={() => handleClaim(d.id)}
                      className="text-xs font-display font-medium bg-navy text-ivory px-3 py-1 rounded-lg hover:bg-navy-mid"
                    >
                      {t('admin.claim')}
                    </button>
                  )}
                  {canResolve && (
                    <button
                      onClick={() => setResolvingId(d.id)}
                      className="text-xs font-display font-medium bg-green-600 text-white px-3 py-1 rounded-lg hover:bg-green-700"
                    >
                      {t('admin.resolve')}
                    </button>
                  )}
                </div>

                {resolvingId === d.id && (
                  <div className="mt-3 pt-3 border-t border-navy/10 space-y-2">
                    <textarea
                      value={verdict}
                      onChange={(e) => setVerdict(e.target.value)}
                      rows={3}
                      placeholder={t('admin.verdictPlaceholder') as string}
                      className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-body text-navy"
                    />
                    <label className="flex items-center gap-2 text-xs font-body text-navy/70">
                      <input
                        type="checkbox"
                        checked={closesDeal}
                        onChange={(e) => setClosesDeal(e.target.checked)}
                      />
                      {t('admin.closeDeal')}
                    </label>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleResolve(d.id)}
                        disabled={!verdict.trim()}
                        className="bg-navy text-ivory font-display font-medium px-3 py-1.5 rounded-lg text-xs hover:bg-navy-mid disabled:opacity-40"
                      >
                        {t('admin.submitVerdict')}
                      </button>
                      <button
                        onClick={() => {
                          setResolvingId(null)
                          setVerdict('')
                        }}
                        className="text-xs font-body text-navy/60 hover:text-navy px-2"
                      >
                        {t('common.cancel')}
                      </button>
                    </div>
                  </div>
                )}

                {d.verdict && (
                  <div className="mt-2 pt-2 border-t border-navy/10">
                    <p className="text-xs font-body text-navy/50">
                      {t('admin.verdictLabel')}:
                    </p>
                    <p className="text-sm font-body text-navy whitespace-pre-wrap">
                      {d.verdict}
                    </p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
