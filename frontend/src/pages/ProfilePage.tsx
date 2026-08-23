import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { me } from '../api/auth'
import { getIdentity, type ArchiveRecord } from '../api/trust'
import ArchiveRecordCard from '../components/ArchiveRecordCard'
import AddressesSection from '../components/AddressesSection'
import PublicPageSection from '../components/PublicPageSection'
import PublishedTripsSection from '../components/PublishedTripsSection'
import EditProfileModal from '../components/EditProfileModal'
import MonoText from '../components/MonoText'

/**
 * T_UX.20 — the account section, and the index of the profile.
 *
 * What is left here is what a counterparty is looking at: who this is, how to
 * reach them, where a parcel goes, and how much of it strangers get to see.
 * Activity, circles, keys, formats and notifications moved to their own
 * sections in the nav beside this one.
 */
export default function ProfilePage() {
  const navigate = useNavigate()
  // T_UX.16 — somebody sent here from a chat to add a missing address gets a
  // way back to that exact conversation. Without it the trip to the profile
  // ends wherever the profile ends, and the sentence they were mid-way through
  // is somebody else's problem.
  const [searchParams] = useSearchParams()
  const returnTo = searchParams.get('return_to')
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
      {/* T_UX.16 return banner */}
      {returnTo && (
        <div className="rounded-card border border-cyan/40 bg-cyan/5 px-4 py-3 flex flex-wrap items-center gap-3">
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
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
              {/* Moved off the page header with T_UX.20: it edits the avatar,
                  the name and the phone, which are all on this card and on no
                  other section. */}
              <button
                type="button"
                onClick={() => setEditOpen(true)}
                className="text-sm font-body font-medium text-cyan hover:underline shrink-0"
              >
                ✎ {t('profile.editButton')}
              </button>
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

          {/* T3.19 — above everything else on the account, because for a
              retired identity this *is* the account: what it did, with dates. */}
          {archive && (
            <ArchiveRecordCard record={archive} memberSince={user?.created_at} />
          )}

          <AddressesSection />
        </div>

        <div className="space-y-4">
          <PublicPageSection />
          <PublishedTripsSection />

          {/* T_UX.19 — disputes stay off the main nav. They matter, but they
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
        </div>
      </div>

      <EditProfileModal open={editOpen} onClose={() => setEditOpen(false)} />
    </div>
  )
}
