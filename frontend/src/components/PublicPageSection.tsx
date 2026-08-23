import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'

/**
 * T3.18 — the public face of this identity: what a counterparty sees before
 * deciding to deal, and how much of it they see.
 *
 * T_UX.20 kept it with the account rather than giving it its own section: this
 * is about being looked at, not about getting in, and the thing being looked at
 * is on the same screen.
 */
export default function PublicPageSection() {
  const { t } = useTranslation()
  const { user, token, setAuth } = useAuthStore()

  /** Visibility applies to every public slice at once, so a click here changes
   *  what the metric endpoints answer too. Saved immediately: this is a
   *  one-field choice, and a Save button would only add a state in which the
   *  radio says one thing and the server another. */
  const handleVisibility = async (value: 'full' | 'minimal' | 'hidden') => {
    if (!user || !token) return
    try {
      const { data } = await updateMe({ public_profile: value })
      setAuth(data, token)
    } catch { /* silent — the radio snaps back on the next read */ }
  }

  if (!user?.nostr_pubkey) return null

  return (
    <div className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
      <h2 className="font-display font-semibold text-base text-navy">
        {user.key_lost ? t('archive.pageTitle') : t('identity.publicTitle')}
      </h2>
      <p className="text-sm font-body text-navy/60">
        {user.key_lost ? t('archive.pageHint') : t('identity.publicHint')}
      </p>
      {/* T3.19 — a retired identity has one question about its page, and it is
          asked in the notice: keep it or close it. Leaving the three-way
          setting here would put two controls over one outcome, and the loser of
          that race is whichever one the user believed. */}
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
  )
}
