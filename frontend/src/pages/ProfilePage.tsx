import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { me, updateMe } from '../api/auth'
import { createInvite, listConnections, listMyInvites, type Connection, type MyInvite } from '../api/social'
import { getIdentity, type ArchiveRecord } from '../api/trust'
import AdminPanelSection from '../components/AdminPanelSection'
import ArchiveRecordCard from '../components/ArchiveRecordCard'
import AddressesSection from '../components/AddressesSection'
import DisplayPrefsSection from '../components/DisplayPrefsSection'
import PublishedTripsSection from '../components/PublishedTripsSection'
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
  // T_UX.16 — somebody sent here from a chat to add a missing address gets a
  // way back to that exact conversation. Without it the trip to the profile
  // ends wherever the profile ends, and the sentence they were mid-way through
  // is somebody else's problem.
  const [searchParams] = useSearchParams()
  const returnTo = searchParams.get('return_to')
  const { t, i18n } = useTranslation()
  const { user, token, setAuth, logout } = useAuthStore()
  const [connections, setConnections] = useState<Connection[]>([])
  const [invites, setInvites] = useState<MyInvite[]>([])
  const [invitesLoading, setInvitesLoading] = useState(false)
  const [creatingInvite, setCreatingInvite] = useState(false)
  const [loading, setLoading] = useState(true)
  const [editOpen, setEditOpen] = useState(false)
  // T3.19 — the owner's own copy of their record. Read from the public endpoint
  // on purpose: what the profile shows and what a counterparty sees are then
  // the same numbers by construction, not by two implementations agreeing.
  const [archive, setArchive] = useState<ArchiveRecord | null>(null)

  // T_UX.6 / T3.32 — `refreshUser` moved out with the sections that needed it:
  // security changes to `ProfileKeysPage`, channel connection to
  // `ChannelsSection`. Nothing on this screen makes the stored user go stale.

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

  // Only for a retired identity, and only once the key is known: on a live
  // account there is no record to fetch, so there is no request either.
  useEffect(() => {
    if (!user?.key_lost || !user.nostr_pubkey) return
    getIdentity(user.nostr_pubkey)
      .then(({ data }) => setArchive(data.archive))
      .catch(() => {})
  }, [user?.key_lost, user?.nostr_pubkey])

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

  /** T3.18 — visibility applies to every public slice at once, so a click here
   *  changes what the metric endpoints answer too. Saved immediately: this is a
   *  one-field choice, and a Save button would only add a state in which the
   *  radio says one thing and the server another. */
  const handleVisibility = async (value: 'full' | 'minimal' | 'hidden') => {
    if (!user || !token) return
    try {
      const { data } = await updateMe({ public_profile: value })
      setAuth(data, token)
    } catch { /* silent — the radio snaps back on the next read */ }
  }

  return (
    <div className="space-y-6">
      {/* T_UX.16 return banner */}
      {returnTo && (
        <div className="mb-4 rounded-card border border-cyan/40 bg-cyan/5 px-4 py-3 flex flex-wrap items-center gap-3">
          <p className="text-sm font-body text-navy/70">{t('address.returnHint')}</p>
          <button
            type="button"
            onClick={() => navigate(returnTo)}
            className="px-4 py-2 rounded-field bg-cyan text-white text-sm font-body"
          >
            {t('address.backToChat')}
          </button>
        </div>
      )}
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
          <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
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
              {/* T_UX.10 — shown even when there is none. It used to render
                  only for accounts that had an address, so an account created
                  by passkey or Nostr key — which by design has no email — saw
                  no mention of email anywhere on this screen and no way to
                  reach the place that adds one. The row is where someone looks
                  for it; the link is where it is actually done, because adding
                  an address needs step-up re-auth (T3.15) and that does not
                  belong in a profile modal. */}
              <div>
                <p className="text-xs font-body font-medium text-navy/40 mb-0.5">
                  {t('profile.email')}
                </p>
                {user?.email ? (
                  <MonoText className="text-sm text-navy break-all">{user.email}</MonoText>
                ) : (
                  <Link
                    to="/profile/keys"
                    className="text-sm font-body text-link underline underline-offset-2"
                  >
                    {t('profile.emailAdd')}
                  </Link>
                )}
              </div>
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

          {/* T3.19 — above the reputation widgets, because for a retired
              identity this *is* the reputation: what it did, with dates. */}
          {archive && (
            <ArchiveRecordCard record={archive} memberSince={user?.created_at} />
          )}

          <UBASection />
          <VerificationSection />
          <TrustCirclesSection />
        </div>

        {/* Right column — addresses + social + keys + notifications */}
        <div className="space-y-4">
          <AddressesSection />
          <DisplayPrefsSection />
          <PublishedTripsSection />
          {/* T_UX.19 — disputes moved off the main nav. They matter, but they
              are rare and slow: a permanent tab for something most accounts
              never open crowds out what people do every day. */}
          <Link
            to="/disputes"
            className="block bg-white rounded-card border border-navy/10 p-4 hover:border-cyan/40 transition-colors"
          >
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('nav.disputes')}
            </p>
            <p className="text-xs font-body text-navy/40 mt-0.5">
              {t('disputes.profileHint')}
            </p>
          </Link>

          <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
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

          {/* T3.18 — the public face of this identity: what a counterparty sees
              before deciding to deal, and how much of it they see. Kept on the
              profile rather than with the keys — this is about being looked at,
              not about getting in. */}
          {user?.nostr_pubkey && (
            <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
              <h2 className="font-display font-semibold text-base text-navy">
                {user.key_lost ? t('archive.pageTitle') : t('identity.publicTitle')}
              </h2>
              <p className="text-sm font-body text-navy/60">
                {user.key_lost ? t('archive.pageHint') : t('identity.publicHint')}
              </p>
              {/* T3.19 — a retired identity has one question about its page, and
                  it is asked in the notice: keep it or close it. Leaving the
                  three-way setting here would put two controls over one outcome,
                  and the loser of that race is whichever one the user believed. */}
              {!user.key_lost && (
                <div className="space-y-1">
                  {(['full', 'minimal', 'hidden'] as const).map((value) => (
                    <label key={value} className="flex items-start gap-2 text-sm font-body">
                      <input
                        type="radio"
                        name="public_profile"
                        checked={(user.public_profile ?? 'full') === value}
                        onChange={() => void handleVisibility(value)}
                        data-testid={`visibility-${value}`}
                        className="mt-1"
                      />
                      <span>
                        <span className="text-navy">{t(`identity.visibility.${value}`)}</span>
                        <span className="block text-xs text-navy/50">
                          {t(`identity.visibilityHint.${value}`)}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
              <Link
                to={`/i/${user.nostr_pubkey}`}
                target="_blank"
                data-testid="identity-public-link"
                className="block w-full text-center border border-navy/20 rounded-field py-2 text-sm font-body text-navy"
              >
                {t('identity.openPublic')}
              </Link>
            </div>
          )}

          {/* T_UX.6 — access and keys moved to their own page. This card is the
              door, not the machinery: the profile answers "who am I to the
              other party", and how I sign in or what I own is a different
              question asked at a different moment. */}
          <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
            <h2 className="font-display font-semibold text-base text-navy">
              {t('profile.keys.title')}
            </h2>
            <p className="text-sm font-body text-navy/60">
              {t('profile.keys.hint')}
            </p>
            <Link
              to="/profile/keys"
              data-testid="profile-keys-link"
              className="block w-full text-center border border-navy/20 rounded-field py-2.5 text-sm font-body text-navy"
            >
              {t('profile.keys.open')}
            </Link>
          </div>

          <div className="bg-white rounded-card border border-navy/10 p-6 space-y-4">
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

          {/* T3.32 — channels and the matrix both live at
              `/profile/notifications`. This card is the door. The profile
              answers "who am I to the other party"; how to reach me and what
              travels down each channel is one task asked at a different
              moment — usually just after something arrived that nobody
              wanted — and wedged between contacts and invite links it was a
              table nobody would go looking for. */}
          <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
            <h2 className="font-display font-semibold text-base text-navy">
              {t('profile.notifications')}
            </h2>
            {/* Not `matrix.hint` — that one says "connected above", which is
                true on the notifications page and false here. */}
            <p className="text-sm font-body text-navy/60">
              {t('profile.matrix.title')}
            </p>
            <Link
              to="/profile/notifications"
              data-testid="profile-notifications-link"
              className="block w-full text-center border border-navy/20 rounded-field py-2.5 text-sm font-body text-navy"
            >
              {t('profile.matrix.open')}
            </Link>
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
