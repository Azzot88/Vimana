import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { me } from '../api/auth'
import { getIdentity, type ArchiveRecord } from '../api/trust'
import ArchiveRecordCard from '../components/ArchiveRecordCard'
import PublicPageSection from '../components/PublicPageSection'
import UBASection from '../components/UBASection'
import VerificationSection from '../components/VerificationSection'
import EditProfileModal from '../components/EditProfileModal'
import MonoText from '../components/MonoText'

/**
 * T_UX.21 — «Аккаунт», and now the whole of what this account is to a
 * counterparty: who they are, what they have done, how far they are trusted,
 * and how much of it strangers get to see.
 *
 * Read top to bottom, which is why this section is a single column while the
 * rest of the profile is two: identity, then the record, then the score, then
 * the proof, then who may look. Two columns would ask the eye to choose.
 *
 * **Two things left with T_UX.21 and it is worth saying why.** The list of
 * published trips went: it existed on the panel and again on `/history`, and a
 * third copy on the showcase was one place too many for data nobody edits here
 * — T_UX.18 had already noticed the duplication. The disputes card became a
 * line in the footer: T_UX.19 moved disputes off the main nav because most
 * accounts never open one, and a full card for that on the front of the profile
 * repeated the mistake it was fixing. The route is unchanged, the door is
 * smaller.
 */
export default function ProfilePage() {
  const { t } = useTranslation()
  const { user, token, setAuth } = useAuthStore()
  const [editOpen, setEditOpen] = useState(false)
  // T3.19 — the owner's own copy of their record. Read from the public endpoint
  // on purpose: what the profile shows and what a counterparty sees are then
  // the same numbers by construction, not by two implementations agreeing.
  const [archive, setArchive] = useState<ArchiveRecord | null>(null)

  useEffect(() => {
    if (user || !token) return
    me()
      .then(({ data }) => setAuth(data, token))
      .catch(() => {})
  }, [])

  // Only for a retired identity, and only once the key is known: on a live
  // account there is no record to fetch, so there is no request either.
  useEffect(() => {
    if (!user?.key_lost || !user.nostr_pubkey) return
    getIdentity(user.nostr_pubkey)
      .then(({ data }) => setArchive(data.archive))
      .catch(() => {})
  }, [user?.key_lost, user?.nostr_pubkey])

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-4 min-w-0">
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.display_name}
                className="w-12 h-12 rounded-full object-cover border border-navy/10"
              />
            ) : (
              <div className="w-12 h-12 rounded-full bg-navy flex items-center justify-center shrink-0">
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
          <button
            type="button"
            onClick={() => setEditOpen(true)}
            className="text-sm font-body font-medium text-cyan hover:underline shrink-0"
          >
            ✎ {t('profile.editButton')}
          </button>
        </div>
        <div className="pt-2 border-t border-navy/10 space-y-2">
          {/* T_UX.10 — shown even when there is none. It used to render only
              for accounts that had an address, so an account created by passkey
              or Nostr key — which by design has no email — saw no mention of
              email anywhere on this screen and no way to reach the place that
              adds one. The row is where someone looks for it; the link is where
              it is actually done, because adding an address needs step-up
              re-auth (T3.15) and that does not belong in a profile modal. */}
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

      {/* T3.19 — above the score, because for a retired identity this *is* the
          record: what it did, with dates. */}
      {archive && <ArchiveRecordCard record={archive} memberSince={user?.created_at} />}

      {/* T_UX.21 — the score and the badges arrived from the retired
          «Уровень активности». They belong on the showcase and always did:
          `Vrf` is a multiplier inside the УБА formula itself, and both answer
          the one question a counterparty asks before dealing. */}
      <UBASection />
      <VerificationSection />

      <PublicPageSection />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pt-1">
        <Link to="/history" className="text-sm font-body text-cyan hover:underline">
          {t('nav.history')}
        </Link>
        <Link to="/disputes" className="text-sm font-body text-cyan hover:underline">
          {t('nav.disputes')}
        </Link>
      </div>

      <EditProfileModal open={editOpen} onClose={() => setEditOpen(false)} />
    </div>
  )
}
