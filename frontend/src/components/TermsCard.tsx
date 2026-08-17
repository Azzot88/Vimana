import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ackCard, type VaultMessage } from '../api/dealvault'
import type { TermsPayload } from '../api/terms'
import MonoText from '../components/MonoText'

/** T3.35 — the contract, rendered from the card that carries it.
 *
 *  Two things this has to show and neither is decoration: the normalised
 *  figures, because a total alone is not comparable between trips; and who is
 *  waiting on whom, because a card that awaits the other side must not offer
 *  you a button that will be refused by the server anyway.
 */
interface Props {
  msg: VaultMessage
  dealId: string
  myRole: 'sender' | 'carrier' | 'recipient' | null
  onChanged: () => void
}

export default function TermsCard({ msg, dealId, myRole, onChanged }: Props) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const payload = (msg.card_payload ?? {}) as TermsPayload
  const norm = payload.normalized
  const agreed = msg.card_kind === 'terms.agreed'
  const awaitingMe = msg.card_state === 'pending' && msg.requires_ack_by === myRole
  const awaitingThem = msg.card_state === 'pending' && !awaitingMe

  const answer = async (decision: 'accepted' | 'declined') => {
    setBusy(true)
    setError('')
    try {
      await ackCard(dealId, msg.id, decision)
      onChanged()
    } catch {
      setError(t('terms.answerFailed'))
    } finally {
      setBusy(false)
    }
  }

  const row = (label: string, value: string | number | null | undefined) =>
    value === null || value === undefined ? null : (
      <div className="flex justify-between gap-4 py-0.5">
        <span className="text-xs font-body text-navy/50">{label}</span>
        <MonoText className="text-xs text-navy">{String(value)}</MonoText>
      </div>
    )

  return (
    <div
      className={`rounded-2xl border p-4 max-w-md ${
        agreed ? 'border-success/40 bg-success/5' : 'border-navy/15 bg-surface'
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm font-display font-semibold text-navy">
          {agreed ? t('terms.agreedTitle') : t('terms.proposalTitle')}
        </span>
        {msg.card_state === 'superseded' && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase bg-navy/10 text-navy/50">
            {t('terms.superseded')}
          </span>
        )}
        {msg.card_state === 'declined' && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase bg-danger/10 text-danger">
            {t('terms.declined')}
          </span>
        )}
      </div>

      {row(t('terms.price'), `${payload.price_total ?? '—'} ${payload.currency ?? ''}`)}
      {row(t('terms.weight'), payload.weight_kg)}
      {row(t('terms.declaredValue'), payload.declared_value)}
      {row(t('terms.paymentMethod'), payload.payment_method)}

      {norm && (
        <div className="mt-2 pt-2 border-t border-navy/10">
          <p className="text-[10px] font-mono uppercase tracking-widest text-navy/40 mb-1">
            {t('terms.normalized')}
          </p>
          {row(t('terms.direction'), norm.direction ?? norm.route)}
          {row(t('terms.distance'), norm.distance_km ? `${norm.distance_km} km` : null)}
          {row(t('terms.chargeableWeight'), norm.chargeable_weight_kg)}
          {row(t('terms.perKg'), norm.price_per_kg)}
          {row(t('terms.perKm'), norm.price_per_km)}
        </div>
      )}

      {payload.below_carrier_minimum && (
        <p className="mt-2 text-xs font-body text-amber">{t('terms.belowMinimum')}</p>
      )}

      {msg.text && (
        <p className="mt-2 text-xs font-body text-navy/60 whitespace-pre-wrap">
          {msg.text}
        </p>
      )}

      {error && <p className="mt-2 text-xs font-body text-danger">{error}</p>}

      {awaitingMe && (
        <div className="mt-3 flex gap-2">
          <button
            disabled={busy}
            onClick={() => answer('accepted')}
            className="px-4 py-2 rounded-lg bg-amber text-navy text-sm font-body disabled:opacity-50"
          >
            {busy ? '...' : t('terms.accept')}
          </button>
          <button
            disabled={busy}
            onClick={() => answer('declined')}
            className="px-4 py-2 rounded-lg border border-navy/15 text-sm font-body disabled:opacity-50"
          >
            {t('terms.decline')}
          </button>
        </div>
      )}

      {awaitingThem && (
        <p className="mt-3 text-xs font-body text-navy/40">{t('terms.awaitingOther')}</p>
      )}
    </div>
  )
}
