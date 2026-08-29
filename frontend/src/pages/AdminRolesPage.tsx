import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import { openRoleOffers, revokeRole, type PendingOffer } from '../api/admin'
import { isSuperuser } from '../lib/permissions'
import { usePrefs } from '../hooks/usePrefs'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'

/**
 * T3.42 — offers waiting for an answer.
 *
 * An offer is a request for a decision somebody else has to make, and before
 * this screen the only trace of an unanswered one was the letter — in the
 * recipient's mailbox, where the person who sent it cannot look. So an offer
 * that was never opened and an offer that was ignored looked identical from
 * here: like nothing at all.
 *
 * The list holds only what is still pending. Answered and withdrawn offers are
 * in the journal of the account they belong to (`/api/admin/users/{id}/roles`),
 * because this page answers "what is waiting on me", not "what has ever
 * happened".
 */
export default function AdminRolesPage() {
  const { t } = useTranslation()
  const me = useAuthStore((s) => s.user)
  const prefs = usePrefs()
  const [offers, setOffers] = useState<PendingOffer[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  if (!isSuperuser(me)) return <Navigate to="/dashboard" replace />

  const load = async () => {
    try {
      const { data } = await openRoleOffers()
      setOffers(data)
      setError('')
    } catch {
      // Not silently empty: an empty list and a failed request read the same
      // on screen, and the second one would hide people waiting for an answer.
      setOffers([])
      setError(t('adminRoles.loadFailed') as string)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const withdraw = async (offer: PendingOffer) => {
    setError('')
    // Same shortcut as the sibling screen, and the same reason: the API needs a
    // reason, this happens a few times a year, and a modal for it is polish.
    const raw = window.prompt(t('adminRoles.withdrawReasonPrompt') as string)
    if (raw === null) return
    const reason = raw.trim()
    if (!reason) {
      setError(t('adminRoles.withdrawReasonRequired') as string)
      return
    }
    setBusy(offer.id)
    try {
      await revokeRole(offer.subject_id, offer.role, reason)
      await load()
    } catch {
      setError(t('adminRoles.withdrawFailed') as string)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-navy">
          {t('adminRoles.title')}
        </h1>
        {/* §9b — what this screen is and what it does not cover. */}
        <p className="text-sm font-body text-navy/60 mt-1">
          {t('adminRoles.description')}
        </p>
      </div>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {offers === null ? (
        <p className="text-sm font-body text-navy/40 text-center py-8">
          {t('common.loading')}
        </p>
      ) : offers.length === 0 ? (
        <div className="bg-white rounded-card border border-navy/10 p-6">
          <p className="text-sm font-body text-navy/50">{t('adminRoles.empty')}</p>
        </div>
      ) : (
        <div className="bg-white rounded-card border border-navy/10 overflow-hidden">
          <table className="w-full text-sm font-body">
            <thead className="bg-ivory">
              <tr className="text-left text-xs font-display font-semibold text-navy/60 uppercase tracking-wide">
                <th className="px-4 py-3">{t('adminRoles.col.who')}</th>
                <th className="px-4 py-3">{t('adminRoles.col.role')}</th>
                <th className="px-4 py-3 hidden sm:table-cell">
                  {t('adminRoles.col.offeredBy')}
                </th>
                <th className="px-4 py-3 hidden md:table-cell">
                  {t('adminRoles.col.when')}
                </th>
                <th className="px-4 py-3 text-right">
                  {t('adminRoles.col.actions')}
                </th>
              </tr>
            </thead>
            <tbody>
              {offers.map((o) => (
                <tr key={o.id} className="border-t border-navy/5">
                  <td className="px-4 py-3">
                    <p className="text-navy font-medium">{o.subject_name || '—'}</p>
                    <MonoText className="text-xs text-navy/40">
                      {o.subject_contact ?? '—'}
                    </MonoText>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-mono border border-amber/50 text-amber px-2 py-0.5 rounded">
                      {t(`roles.names.${o.role}`)}
                    </span>
                    {o.reason && (
                      <p className="text-xs font-body text-navy/50 mt-1">{o.reason}</p>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell text-navy/70">
                    {o.actor_name || '—'}
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    {/* T_UX.14 — dates follow the account's setting, not the
                        browser and not ISO. A screen that formats its own is
                        the reason that setting reads as not applying anywhere. */}
                    <MonoText className="text-xs text-navy/50">
                      {prefs.dateTime(o.created_at)}
                    </MonoText>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => withdraw(o)}
                      disabled={busy === o.id}
                      className="text-xs font-display font-medium px-3 py-1 rounded-field bg-navy/10 text-navy hover:bg-navy/20 disabled:opacity-50"
                    >
                      {t('adminRoles.withdraw')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
