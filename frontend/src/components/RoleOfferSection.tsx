import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { acceptRole, declineRole, myRoles, type RoleGrant } from '../api/roles'

/**
 * T3.42 — a role proposed to this account, and the answer to it.
 *
 * The section renders nothing at all when there is no offer and the account
 * holds no role beyond `user`. A permanently visible "you have no roles" box
 * would be a row of furniture for something that happens to almost nobody.
 *
 * **The wording never says the role has arrived** (DESIGNGUIDELINES §9.1). It
 * has not: the account holds exactly the rights it held before, and every
 * endpoint the role guards refuses until Accept is pressed. Calling it
 * "assigned" here would describe a state the backend does not implement.
 */
export default function RoleOfferSection() {
  const { t } = useTranslation()
  const [role, setRole] = useState<string>('user')
  const [offers, setOffers] = useState<RoleGrant[] | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const { data } = await myRoles()
      setRole(data.role)
      setOffers(data.offers)
      setError('')
    } catch {
      // Not silently empty: an empty list and a failed request look identical
      // on screen, and the second one would quietly hide an offer somebody is
      // waiting on an answer to.
      setOffers([])
      setError(t('roles.loadFailed') as string)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const answer = async (r: string, accept: boolean) => {
    setBusy(r)
    setError('')
    try {
      await (accept ? acceptRole(r) : declineRole(r))
      await load()
    } catch {
      setError(t('roles.answerFailed') as string)
    } finally {
      setBusy('')
    }
  }

  const hasOffers = (offers?.length ?? 0) > 0
  if (offers !== null && !hasOffers && role === 'user' && !error) return null

  return (
    <div className="bg-white rounded-card border border-navy/10 p-5 space-y-3">
      <h2 className="font-display font-semibold text-lg text-navy">
        {t('roles.title')}
      </h2>
      {/* §9b — what this is and where it applies, before any control. */}
      <p className="text-sm font-body text-navy/60">{t('roles.description')}</p>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {role !== 'user' && (
        <p className="text-sm font-body text-navy">
          {t('roles.current')}{' '}
          <span className="font-mono text-navy">{t(`roles.names.${role}`)}</span>
        </p>
      )}

      {(offers ?? []).map((offer) => (
        <div
          key={offer.id}
          className="border border-amber/40 bg-amber/5 rounded-field p-4 space-y-2"
        >
          <p className="font-display font-medium text-navy">
            {t('roles.offeredTitle', { role: t(`roles.names.${offer.role}`) })}
          </p>
          <p className="text-sm font-body text-navy/70">
            {t(`roles.what.${offer.role}`)}
          </p>
          {offer.actor_name && (
            <p className="text-xs font-body text-navy/50">
              {t('roles.offeredBy', { name: offer.actor_name })}
            </p>
          )}
          {offer.reason && (
            <p className="text-xs font-body text-navy/50">{offer.reason}</p>
          )}
          {/* Said plainly rather than implied by the buttons: until one of them
              is pressed, nothing about the account has changed. */}
          <p className="text-xs font-body text-navy/50">{t('roles.notYet')}</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              onClick={() => answer(offer.role, true)}
              disabled={busy === offer.role}
              data-testid={`role-accept-${offer.role}`}
              className="text-sm font-display font-medium bg-amber text-white px-4 py-2 rounded-field hover:opacity-90 disabled:opacity-50"
            >
              {t('roles.accept')}
            </button>
            <button
              onClick={() => answer(offer.role, false)}
              disabled={busy === offer.role}
              data-testid={`role-decline-${offer.role}`}
              className="text-sm font-display font-medium border border-navy/20 text-navy px-4 py-2 rounded-field hover:bg-ivory disabled:opacity-50"
            >
              {t('roles.decline')}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
