import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { updateMe } from '../api/auth'
import {
  acceptRecipientOffer,
  declineRecipientOffer,
  myRecipientOffers,
  type RecipientOffer,
} from '../api/participants'
import { usePrefs } from '../hooks/usePrefs'
import { useAuthStore } from '../stores/auth'
import MonoText from './MonoText'

/**
 * T3.12.05 — the role of recipient, offered to this account, and the answer.
 *
 * Owner, 2026-09-14: «роль предлагается, а не назначается». Nothing of the deal
 * is this person's until they accept — the card shows only what they need to
 * recognise the parcel (route, sender, what is sent) and says so, so the
 * absence of a chat does not read as a fault.
 *
 * **Three answers, not two.** «Отказаться и больше не предлагать мне эту роль»
 * sets the account setting in the same press; the toggle below it is the same
 * setting, reachable without an offer to refuse.
 *
 * Functions (PROJECT §6.2a):
 * - `RecipientOfferCard({ offer, onDeclined })` — one offer and its answers.
 *   Called by: `RecipientOfferSection`, `pages/JoinDealPage`.
 * - `RecipientOfferSection()` — default export. Called by: `pages/ProfilePage`.
 */
export function RecipientOfferCard({
  offer,
  onDeclined,
}: {
  offer: RecipientOffer
  onDeclined: (offer: RecipientOffer) => void
}) {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const answer = async (kind: 'accept' | 'decline' | 'refuse') => {
    setBusy(true)
    setError('')
    try {
      if (kind === 'accept') {
        const { data } = await acceptRecipientOffer(offer.id)
        navigate(`/deals/${data.deal_id}/vault`)
        return
      }
      const { data } = await declineRecipientOffer(offer.id, kind === 'refuse')
      onDeclined(data)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('recipientOffer.answerFailed'))
    } finally {
      setBusy(false)
    }
  }

  const row = (label: string, value: string | null | undefined) =>
    value ? (
      <div className="flex justify-between gap-4 py-0.5">
        <span className="text-xs font-body text-navy/45">{label}</span>
        <span className="text-xs font-body text-navy text-right">{value}</span>
      </div>
    ) : null

  return (
    <div
      data-testid="recipient-offer"
      className="rounded-field border border-cyan/30 bg-cyan/5 p-4 space-y-3"
    >
      <div>
        {offer.route && <MonoText className="text-sm text-navy font-medium">{offer.route}</MonoText>}
        {offer.depart_at && (
          <MonoText className="block text-xs text-navy/50">
            {prefs.dateTime(offer.depart_at)}
          </MonoText>
        )}
      </div>
      <div>
        {row(t('recipientOffer.from'), offer.sender_name)}
        {row(t('recipientOffer.cargo'), offer.cargo_description)}
      </div>
      <p className="text-[11px] font-body text-navy/50">{t('recipientOffer.nothingYet')}</p>
      {error && <p className="text-xs font-body text-danger">{error}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void answer('accept')}
          className="bg-amber text-white font-display font-medium px-4 py-2 rounded-field text-sm hover:opacity-90 disabled:opacity-50"
        >
          {t('recipientOffer.accept')}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void answer('decline')}
          className="border border-navy/20 text-navy font-body px-4 py-2 rounded-field text-sm hover:bg-ivory disabled:opacity-50"
        >
          {t('recipientOffer.decline')}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void answer('refuse')}
          className="text-xs font-body text-navy/50 hover:text-navy underline decoration-navy/20 underline-offset-2 disabled:opacity-50"
        >
          {t('recipientOffer.declineRefuse')}
        </button>
      </div>
    </div>
  )
}

export default function RecipientOfferSection() {
  const { t } = useTranslation()
  const { user, token, setAuth } = useAuthStore()
  const [offers, setOffers] = useState<RecipientOffer[]>([])
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const { data } = await myRecipientOffers()
      setOffers(data)
    } catch {
      setOffers([])
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const toggleRefuse = async (next: boolean) => {
    setError('')
    try {
      const { data } = await updateMe({ refuses_recipient_offers: next })
      if (token) setAuth(data, token)
    } catch {
      setError(t('prefs.saveFailed'))
    }
  }

  return (
    <section className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
      <div>
        <h2 className="font-display font-semibold text-sm text-navy">
          {t('recipientOffer.sectionTitle')}
        </h2>
        <p className="text-[11px] font-body text-navy/50 mt-0.5">
          {t('recipientOffer.sectionHint')}
        </p>
      </div>
      {offers.map((offer) => (
        <RecipientOfferCard
          key={offer.id}
          offer={offer}
          onDeclined={(answered) =>
            setOffers((prev) => prev.filter((o) => o.id !== answered.id))
          }
        />
      ))}
      <label className="flex items-start gap-2 text-sm font-body text-navy">
        <input
          type="checkbox"
          className="mt-1"
          checked={Boolean(user?.refuses_recipient_offers)}
          onChange={(e) => void toggleRefuse(e.target.checked)}
        />
        <span>
          {t('recipientOffer.refuseToggle')}
          <span className="block text-[11px] text-navy/50">{t('recipientOffer.refuseHint')}</span>
        </span>
      </label>
      {error && <p className="text-xs font-body text-danger">{error}</p>}
    </section>
  )
}
