import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { getIdentity, type PublicIdentity } from '../api/trust'
import { shortKey } from '../lib/identity'
import MonoText from '../components/MonoText'
import UBAChip from '../components/UBAChip'

/**
 * T3.18 — an identity, by its key, readable by anyone.
 *
 * Outside the protected routes on purpose: this is the page a counterparty
 * opens before deciding whether to deal, and asking them to register first
 * would defeat the point of having it.
 *
 * Everything here is already public elsewhere in the product; what is new is
 * that it has an address. The address is the npub, because the key *is* the
 * identity (`D-KEY-TIERS`) — an internal row id in a shareable link would name
 * something only our database knows about.
 *
 * Every claim carries its date (`D-EVIDENCE-DECAYS`): "member since", and — if
 * it happened — when the key changed. A bare badge asserts more than the fact.
 */
export default function IdentityPage() {
  const { npub = '' } = useParams()
  const { t, i18n } = useTranslation()
  const [identity, setIdentity] = useState<PublicIdentity | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'missing'>('loading')

  useEffect(() => {
    getIdentity(npub)
      .then(({ data }) => {
        setIdentity(data)
        setState('ready')
      })
      // 404 covers both "no such key" and "hidden by its owner", and the page
      // must not tell them apart — distinguishing them would answer the very
      // question hiding refuses to answer.
      .catch(() => setState('missing'))
  }, [npub])

  if (state === 'loading') {
    return (
      <div className="min-h-screen bg-ivory flex items-center justify-center px-4">
        <MonoText className="text-sm text-navy/40">{t('common.loading')}</MonoText>
      </div>
    )
  }

  if (state === 'missing' || !identity) {
    return (
      <div className="min-h-screen bg-ivory flex items-center justify-center px-4">
        <div className="max-w-sm text-center space-y-3">
          <h1 className="font-display font-bold text-xl text-navy">
            {t('identity.notFoundTitle')}
          </h1>
          <p className="text-sm font-body text-navy/60">{t('identity.notFoundBody')}</p>
          <Link to="/" className="text-sm font-body text-cyan hover:underline">
            {t('identity.toHome')}
          </Link>
        </div>
      </div>
    )
  }

  const minimal = identity.visibility === 'minimal'

  return (
    <div className="min-h-screen bg-ivory px-4 py-10">
      <div className="max-w-lg mx-auto space-y-4">
        <div className="bg-white rounded-2xl border border-navy/10 p-6 space-y-4">
          <div className="flex items-center gap-4">
            {identity.avatar_url ? (
              <img
                src={identity.avatar_url}
                alt={identity.display_name ?? ''}
                className="w-14 h-14 rounded-full object-cover border border-navy/10"
              />
            ) : (
              <div className="w-14 h-14 rounded-full bg-navy flex items-center justify-center">
                <span className="text-ivory font-display font-bold text-xl">
                  {identity.display_name?.[0]?.toUpperCase() ?? '·'}
                </span>
              </div>
            )}
            <div className="min-w-0 flex-1">
              <h1 className="font-display font-semibold text-lg text-navy truncate">
                {identity.display_name ?? t('identity.unnamed')}
              </h1>
              <MonoText className="text-xs text-navy/40" >
                <span title={identity.npub}>{shortKey(identity.npub)}</span>
              </MonoText>
            </div>
            {identity.key_lost && (
              <span
                data-testid="identity-key-lost"
                className="text-xs font-body px-2 py-0.5 rounded bg-navy/10 text-navy/50"
              >
                {t('trips.keyLost')}
              </span>
            )}
          </div>

          {minimal ? (
            /* The owner chose to be a fact rather than a portrait. Saying so is
               better than rendering a page full of blanks. */
            <p className="text-sm font-body text-navy/60">{t('identity.minimalBody')}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <UBAChip uba={identity.uba} level={identity.uba_level as never} />
                {identity.highest_verification_level && (
                  <span className="text-xs font-body px-2 py-0.5 rounded bg-cyan/10 text-cyan">
                    {t(`verification.level.${identity.highest_verification_level}`)}
                  </span>
                )}
              </div>

              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm font-body">
                <div>
                  <dt className="text-xs text-navy/50">{t('identity.memberSince')}</dt>
                  <dd className="text-navy">
                    {identity.member_since
                      ? new Date(identity.member_since).toLocaleDateString(i18n.language)
                      : '—'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-navy/50">{t('identity.dealtWith')}</dt>
                  <dd className="text-navy">{identity.dealt_with_count ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-xs text-navy/50">{t('identity.vouchedFor')}</dt>
                  <dd className="text-navy">{identity.verifications_issued_count ?? 0}</dd>
                </div>
                <div>
                  <dt className="text-xs text-navy/50">{t('identity.vouchedBy')}</dt>
                  <dd className="text-navy">
                    {identity.verifications_received_count ?? 0}
                  </dd>
                </div>
              </dl>
            </>
          )}

          {/* T3.23 — said plainly, with its date. Records signed before this
              are valid and belong to a key this identity no longer holds. */}
          {identity.identity_changed_at && (
            <div className="bg-navy/5 rounded-lg px-3 py-2 space-y-0.5">
              <p className="text-xs font-body text-navy/70" data-testid="identity-changed">
                {t('identity.keyChangedOn', {
                  date: new Date(identity.identity_changed_at).toLocaleDateString(
                    i18n.language,
                  ),
                })}
              </p>
              {identity.previous_npub && (
                <p className="text-xs font-body text-navy/50">
                  {t('profile.identity.previousKey')}{' '}
                  <span className="font-mono" title={identity.previous_npub}>
                    {shortKey(identity.previous_npub)}
                  </span>
                </p>
              )}
            </div>
          )}
        </div>

        <p className="text-xs font-body text-navy/40 text-center">
          {t('identity.footer')}
        </p>
      </div>
    </div>
  )
}
