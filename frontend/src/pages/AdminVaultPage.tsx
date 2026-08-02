import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useParams } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { readVaultAsArbiter } from '../api/admin'
import type { VaultMessage } from '../api/dealvault'
import MonoText from '../components/MonoText'

export default function AdminVaultPage() {
  const { t, i18n } = useTranslation()
  const { dealId } = useParams<{ dealId: string }>()
  const user = useAuthStore((s) => s.user)
  const [messages, setMessages] = useState<VaultMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  if (user?.role !== 'arbiter' && user?.role !== 'superuser') {
    return <Navigate to="/dashboard" replace />
  }

  useEffect(() => {
    if (!dealId) return
    ;(async () => {
      try {
        const { data } = await readVaultAsArbiter(dealId, { limit: 100 })
        setMessages(data.items)
      } catch {
        setError(t('admin.vaultError'))
      } finally {
        setLoading(false)
      }
    })()
  }, [dealId, t])

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex items-center gap-3">
        <Link
          to="/admin/disputes"
          className="text-xs font-body text-navy/40 hover:text-navy"
        >
          ← {t('admin.backToDisputes')}
        </Link>
      </div>
      <div className="bg-amber/10 border border-amber/40 rounded-xl p-4">
        <p className="text-sm font-body text-navy">
          ⚖️ {t('admin.arbiterAudit')}
        </p>
      </div>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {loading ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('common.loading')}
        </p>
      ) : (
        <div className="bg-white rounded-xl border border-navy/10 p-4 space-y-3">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`border-l-2 pl-3 ${
                m.is_system ? 'border-danger/40 bg-danger/5 -mx-4 px-4 py-2' : 'border-navy/10'
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <MonoText className="text-xs text-navy/40">
                  {m.is_system
                    ? t('admin.systemMessage')
                    : m.sender_id?.slice(0, 8) ?? '—'}
                </MonoText>
                <MonoText className="text-xs text-navy/40">
                  {new Date(m.created_at).toLocaleString(i18n.language)}
                </MonoText>
              </div>
              {m.text && (
                <p className="text-sm font-body text-navy whitespace-pre-wrap mt-1">
                  {m.text}
                </p>
              )}
              {m.attachments.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {m.attachments.map((a) => (
                    <MonoText key={a.id} className="text-xs text-navy/50">
                      📎 {a.kind}
                    </MonoText>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
