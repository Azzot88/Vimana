import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { me, updateMe, getTelegramLink } from '../api/auth'
import { createInvite, listConnections, listMyInvites, type Connection, type MyInvite } from '../api/social'
import AdminPanelSection from '../components/AdminPanelSection'
import AddressesSection from '../components/AddressesSection'
import EditProfileModal from '../components/EditProfileModal'
import MonoText from '../components/MonoText'
import TrustCirclesSection from '../components/TrustCirclesSection'
import UBASection from '../components/UBASection'
import VerificationSection from '../components/VerificationSection'
import { APP_VERSION } from '../version'

function formatRemaining(expiresAt: string): string {
  const remainingMs = new Date(expiresAt).getTime() - Date.now()
  if (remainingMs <= 0) return '0д'
  const totalHours = Math.floor(remainingMs / 3_600_000)
  const days = Math.floor(totalHours / 24)
  const hours = totalHours % 24
  if (days === 0) return `${hours}ч`
  return `${days}д ${hours}ч`
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const { user, token, setAuth, logout } = useAuthStore()
  const [connections, setConnections] = useState<Connection[]>([])
  const [invites, setInvites] = useState<MyInvite[]>([])
  const [invitesLoading, setInvitesLoading] = useState(false)
  const [creatingInvite, setCreatingInvite] = useState(false)
  const [loading, setLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)

  // T_UX.6 — `refreshUser` moved to `ProfileKeysPage` along with the sections
  // that needed it: only a security change makes the stored user go stale, and
  // those now happen on the other screen.

  const loadInvites = async () => {
    setInvitesLoading(true)
    try {
      const { data } = await listMyInvites()
      setInvites(data)
    } catch { /* silent */ }
    finally { setInvitesLoading(false) }
  }

  useEffect(() => {
    const load = async () => {
      try {
        if (!user && token) {
          const { data } = await me()
          setAuth(data, token)
        }
        const [conns] = await Promise.all([listConnections(), loadInvites()])
        setConnections(conns.data)
      } catch {
        // silent
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const handleCreateInvite = async () => {
    setCreatingInvite(true)
    try {
      await createInvite()
      await loadInvites()
    } catch { /* silent */ }
    finally { setCreatingInvite(false) }
  }

  const copyInviteLink = (token: string) => {
    const url = `${window.location.origin}/invite/${token}`
    navigator.clipboard?.writeText(url).catch(() => {})
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleToggle = async (field: 'notify_email' | 'notify_telegram' | 'notify_whatsapp') => {
    if (!user) return
    const newVal = !user[field]
    try {
      const { data } = await updateMe({ [field]: newVal })
      setAuth(data, token!)
    } catch { /* silent */ }
  }

  const handleConnectTelegram = async () => {
    try {
      const { data } = await getTelegramLink()
      window.open(data.link, '_blank')
    } catch { /* silent */ }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display font-bold text-2xl text-navy">{t('profile.title')}</h1>
        <button
          type="button"
          onClick={() => setEditOpen(true)}
          className="text-sm font-body font-medium text-cyan hover:underline"
        >
          ✎ {t('profile.editButton')}
        </button>
      </div>

      {/* Two-column Bento layout (T_UX.1 rule) — desktop/tablet 2-col,
          phone/landscape-narrow single. Achieved via `md:` breakpoint since
          the sections themselves are already fully mobile-friendly and the
          BentoGrid coarse-pointer rule only really matters for widgets that
          break at that pointer type. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
        {/* Left column — identity + reputation */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-3">
            <div className="flex items-center gap-4">
              {user?.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={user.display_name}
                  className="w-12 h-12 rounded-full object-cover border border-navy/10"
                />
              ) : (
                <div className="w-12 h-12 rounded-full bg-navy flex items-center justify-center">
                  <span className="text-ivory font-display font-bold text-lg">
                    {user?.display_name?.[0]?.toUpperCase() ?? '?'}
                  </span>
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="font-display font-semibold text-lg text-navy truncate">
                  {user?.display_name}
                </p>
                <p className="text-xs font-mono text-navy/40">
                  {user?.active_mode === 'carrier'
                    ? t('dashboard.carrier')
                    : t('dashboard.sender')}
                </p>
              </div>
            </div>
            <div className="pt-2 border-t border-navy/10 space-y-2">
              {user?.email && (
                <div>
                  <p className="text-xs font-body font-medium text-navy/40 mb-0.5">
                    {t('profile.email')}
                  </p>
                  <MonoText className="text-sm text-navy break-all">{user.email}</MonoText>
                </div>
              )}
              {user?.phone && (
                <div>
                  <p className="text-xs font-body font-medium text-navy/40 mb-0.5">
                    {t('auth.phone')}
                  </p>
                  <MonoText className="text-sm text-navy">{user.phone}</MonoText>
                </div>
              )}
            </div>
          </div>

          <UBASection />
          <VerificationSection />
          <TrustCirclesSection />
        </div>

        {/* Right column — addresses + social + keys + notifications */}
        <div className="space-y-4">
          <AddressesSection />

          <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-display font-semibold text-base text-navy">
                {t('profile.contacts')}
              </h2>
              <Link to="/invite" className="text-xs font-body text-cyan hover:underline">
                {t('profile.invite')}
              </Link>
            </div>
            {loading ? (
              <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
            ) : connections.length === 0 ? (
              <p className="text-sm font-body text-navy/40">{t('profile.noContacts')}</p>
            ) : (
              <div className="space-y-2">
                {connections.map((conn) => (
                  <div
                    key={conn.id}
                    className="flex items-center justify-between py-2 border-b border-navy/5 last:border-0"
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 rounded-full bg-ivory border border-navy/10 flex items-center justify-center">
                        <span className="text-xs font-display font-bold text-navy">
                          {conn.display_name[0]?.toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <p className="text-sm font-body text-navy">{conn.display_name}</p>
                        <p className="text-xs font-mono text-navy/40">
                          {conn.is_carrier ? t('dashboard.carrier') : t('dashboard.sender')}
                        </p>
                      </div>
                    </div>
                    <MonoText className="text-xs text-navy/30">
                      {new Date(conn.connected_at).toLocaleDateString(i18n.language)}
                    </MonoText>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* T_UX.6 — access and keys moved to their own page. This card is the
              door, not the machinery: the profile answers "who am I to the
              other party", and how I sign in or what I own is a different
              question asked at a different moment. */}
          <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-3">
            <h2 className="font-display font-semibold text-base text-navy">
              {t('profile.keys.title')}
            </h2>
            <p className="text-sm font-body text-navy/60">
              {t('profile.keys.hint')}
            </p>
            <Link
              to="/profile/keys"
              data-testid="profile-keys-link"
              className="block w-full text-center border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
            >
              {t('profile.keys.open')}
            </Link>
          </div>

          <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-display font-semibold text-base text-navy">
                {t('profile.invites')}
              </h2>
              <button
                type="button"
                onClick={handleCreateInvite}
                disabled={creatingInvite}
                className="text-xs font-body text-cyan hover:underline disabled:opacity-50"
              >
                {creatingInvite ? t('common.sending') : t('profile.inviteCreate')}
              </button>
            </div>
            {invitesLoading ? (
              <MonoText className="text-xs text-navy/40">{t('common.loading')}</MonoText>
            ) : invites.length === 0 ? (
              <p className="text-sm font-body text-navy/40">{t('profile.noInvites')}</p>
            ) : (
              <div className="space-y-2">
                {invites.map((inv) => {
                  const statusColor =
                    inv.status === 'accepted'
                      ? 'bg-green-100 text-green-700'
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

          <div className="bg-white rounded-xl border border-navy/10 p-6 space-y-4">
            <h2 className="font-display font-semibold text-base text-navy">
              {t('profile.notifications')}
            </h2>
            {([
              { key: 'notify_email' as const, label: t('profile.email'), sub: user?.email ?? '—' },
              {
                key: 'notify_telegram' as const,
                label: t('profile.telegram'),
                sub: user?.telegram_chat_id
                  ? t('profile.telegramConnected')
                  : t('profile.telegramNotConnected'),
              },
              {
                key: 'notify_whatsapp' as const,
                label: t('profile.whatsapp'),
                sub: user?.whatsapp_number ?? t('profile.whatsappNotSet'),
              },
            ]).map(({ key, label, sub }) => (
              <div key={key} className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-body text-navy">{label}</p>
                  <p className="text-xs font-mono text-navy/40">{sub}</p>
                </div>
                <button
                  onClick={() => handleToggle(key)}
                  className={`w-10 h-6 rounded-full transition-colors ${user?.[key] ? 'bg-cyan' : 'bg-navy/20'}`}
                >
                  <span
                    className={`block w-4 h-4 bg-white rounded-full mx-auto transition-transform ${user?.[key] ? 'translate-x-2' : '-translate-x-2'}`}
                  />
                </button>
              </div>
            ))}
            {user?.notify_telegram && !user?.telegram_chat_id && (
              <button
                onClick={handleConnectTelegram}
                className="w-full text-sm font-body text-cyan border border-cyan/30 rounded-lg py-2 hover:bg-cyan/5 transition-colors"
              >
                {t('profile.connectTelegram')}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Admin panel full-width if user has access (arbiter/superuser) */}
      <AdminPanelSection />

      <div className="flex items-center justify-between pt-2">
        <button
          onClick={handleLogout}
          className="text-sm font-body text-navy/40 hover:text-navy transition-colors"
        >
          {t('profile.logout')}
        </button>
        <MonoText className="text-xs text-navy/20">v{APP_VERSION}</MonoText>
      </div>

      <EditProfileModal open={editOpen} onClose={() => setEditOpen(false)} />
    </div>
  )
}
