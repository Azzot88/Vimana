import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { claimInvite, type RecipientOffer } from '../api/participants'
import { RecipientOfferCard } from '../components/RecipientOfferSection'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'
import { withReturn } from '../lib/returnTo'

/** T3.3 / T3.12.05 — landing page for a `/join/deal/:token` invite link.
 *
 * Not logged in → `/login?returnUrl=` back here (T_UX.30 — it said `next`, which
 * the sign-in page never read, and the offer was lost on the way). Logged in →
 * the link is bound to this person and **the offer is shown** (owner, 2026-09-14): opening a link used to
 * make somebody the recipient on the spot, which is exactly «меня вписали в
 * чужую сделку». Now they see the route, the sender and what is sent, and
 * accept, decline, or decline and ask not to be offered the role again.
 *
 * An offer already accepted by this person goes straight to the deal.
 */
export default function JoinDealPage() {
  const { t } = useTranslation()
  const { token } = useParams<{ token: string }>()
  const nav = useNavigate()
  const user = useAuthStore((s) => s.user)
  const [offer, setOffer] = useState<RecipientOffer | null>(null)
  const [declined, setDeclined] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!token) return
    if (!user) {
      nav(withReturn('/login', `/join/deal/${token}`), { replace: true })
      return
    }
    claimInvite(token)
      .then(({ data }) => {
        if (data.state === 'accepted') {
          nav(`/deals/${data.deal_id}/vault`, { replace: true })
          return
        }
        setOffer(data)
      })
      .catch((err) => {
        const detail = err?.response?.data?.detail
        setError(typeof detail === 'string' ? detail : t('recipient.joinError'))
      })
  }, [token, user])

  return (
    <div className="max-w-md mx-auto py-16 space-y-4">
      <h1 className="font-display font-bold text-xl text-navy text-center">
        {t('recipientOffer.title')}
      </h1>
      {error && <p className="text-sm font-body text-danger text-center">{error}</p>}
      {!error && !offer && (
        <MonoText className="block text-center text-xs text-navy/40">
          {t('common.loading')}
        </MonoText>
      )}
      {offer && !declined && (
        <RecipientOfferCard offer={offer} onDeclined={() => setDeclined(true)} />
      )}
      {declined && (
        <p className="text-sm font-body text-navy/60 text-center">
          {t('recipientOffer.declined')}
        </p>
      )}
    </div>
  )
}
