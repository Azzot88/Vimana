import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createInvite, listMyInvites, type MyInvite } from '../api/social'
import MonoText from './MonoText'

function formatRemaining(expiresAt: string): string {
  const remainingMs = new Date(expiresAt).getTime() - Date.now()
  if (remainingMs <= 0) return '0д'
  const totalHours = Math.floor(remainingMs / 3_600_000)
  const days = Math.floor(totalHours / 24)
  const hours = totalHours % 24
  if (days === 0) return `${hours}ч`
  return `${days}д ${hours}ч`
}

/** T_UX.20 — lifted out of `ProfilePage` unchanged. An invite is how a circle
 *  gets one person wider, so it sits with the circles rather than three cards
 *  below them. */
export default function InvitesSection() {
  const { t } = useTranslation()
  const [invites, setInvites] = useState<MyInvite[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await listMyInvites()
      setInvites(data)
    } catch { /* silent */ }
    finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [])

  const handleCreate = async () => {
    setCreating(true)
    try {
      await createInvite()
      await load()
    } catch { /* silent */ }
    finally { setCreating(false) }
  }

  const copyInviteLink = (token: string) => {
    const url = `${window.location.origin}/invite/${token}`
    navigator.clipboard?.writeText(url).catch(() => {})
  }

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4 h-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display font-semibold text-base text-navy">
            {t('profile.invites')}
          </h2>
          {/* T_UX.22 — a line under every heading (DESIGNGUIDELINES §9b). */}
          <p className="text-xs font-body text-navy/50 mt-0.5">{t('profile.invitesDesc')}</p>
        </div>
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className="text-xs font-body text-cyan hover:underline disabled:opacity-50 shrink-0"
        >
          {creating ? t('common.sending') : t('profile.inviteCreate')}
        </button>
      </div>
      {loading ? (
        <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
      ) : invites.length === 0 ? (
        <p className="text-sm font-body text-navy/40">{t('profile.noInvites')}</p>
      ) : (
        <div className="space-y-2">
          {invites.map((inv) => {
            const statusColor =
              inv.status === 'accepted'
                ? 'bg-success/10 text-success'
                : inv.status === 'expired'
                ? 'bg-navy/10 text-navy/50'
                : 'bg-cyan/10 text-cyan'
            return (
              <div
                key={inv.token}
                className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0 gap-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs font-mono px-2 py-0.5 rounded ${statusColor}`}>
                      {t(`profile.inviteStatus.${inv.status}`)}
                    </span>
                    {inv.status === 'pending' && (
                      <span className="text-xs font-mono text-navy/40">
                        {t('profile.inviteExpiresIn', { time: formatRemaining(inv.expires_at) })}
                      </span>
                    )}
                    {inv.status === 'accepted' && inv.accepted_by_display_name && (
                      <span className="text-xs font-body text-navy/60">
                        → {inv.accepted_by_display_name}
                      </span>
                    )}
                  </div>
                  <MonoText className="text-xs text-navy/30 truncate mt-0.5">
                    {inv.token.slice(0, 24)}…
                  </MonoText>
                </div>
                {inv.status === 'pending' && (
                  <button
                    type="button"
                    onClick={() => copyInviteLink(inv.token)}
                    className="text-xs font-body text-cyan/70 hover:text-cyan shrink-0"
                  >
                    {t('profile.inviteCopy')}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
