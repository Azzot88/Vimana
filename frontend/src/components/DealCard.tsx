import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ackCard, uploadAttachment, type VaultMessage } from '../api/dealvault'
import { kindKey, specForKind, type DealRole } from '../lib/cardForms'
import MonoText from '../components/MonoText'

/** T3.36–T3.39 — one renderer for every card that is not the contract.
 *
 *  Three states have to be visually distinct, because confusing them costs
 *  somebody a delivery: *you owe an answer*, *they owe an answer*, and *this is
 *  settled*. A declaration still missing its photo is a fourth — it looks
 *  finished to its author and cannot be confirmed by anyone.
 */
interface Props {
  msg: VaultMessage
  dealId: string
  myRole: DealRole | null
  mine: boolean
  onChanged: () => void
}

export default function DealCard({ msg, dealId, myRole, mine, onChanged }: Props) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const kind = msg.card_kind ?? ''
  const spec = specForKind(kind)
  const payload = (msg.card_payload ?? {}) as Record<string, unknown>
  const needsPhoto = Boolean(spec?.needsPhoto) && msg.attachments.length === 0
  // A declaration whose evidence has not arrived is not answerable yet: the
  // server refuses the ack with 422. Offering the button anyway is the exact
  // failure this component is supposed to avoid — a control that does nothing.
  const awaitingMe =
    msg.card_state === 'pending' && msg.requires_ack_by === myRole && !needsPhoto
  const awaitingThem = msg.card_state === 'pending' && !awaitingMe && !needsPhoto

  const answer = async (decision: 'accepted' | 'declined') => {
    setBusy(true)
    setError('')
    try {
      await ackCard(dealId, msg.id, decision)
      onChanged()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('cards.answerFailed'))
    } finally {
      setBusy(false)
    }
  }

  const attach = async (file: File) => {
    if (!spec?.needsPhoto) return
    setBusy(true)
    setError('')
    try {
      await uploadAttachment(dealId, msg.id, file, spec.needsPhoto)
      onChanged()
    } catch {
      setError(t('cards.uploadFailed'))
    } finally {
      setBusy(false)
    }
  }

  const tone = awaitingMe
    ? 'border-amber/50 bg-amber/5'
    : msg.card_state === 'declined'
      ? 'border-danger/40 bg-danger/5'
      : 'border-navy/15 bg-surface'

  return (
    <div className={`rounded-2xl border p-4 max-w-md ${tone}`}>
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="text-sm font-display font-semibold text-navy">
          {t(kindKey(kind), kind)}
        </span>
        {msg.card_state && msg.card_state !== 'pending' && (
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase bg-navy/10 text-navy/50">
            {t(`cards.state.${msg.card_state}`, msg.card_state)}
          </span>
        )}
      </div>

      {Object.entries(payload).map(([key, value]) =>
        value === null || value === undefined || typeof value === 'object' ? null : (
          <div key={key} className="flex justify-between gap-4 py-0.5">
            <span className="text-xs font-body text-navy/50">
              {t(`cards.field.${key}`, key)}
            </span>
            <MonoText className="text-xs text-navy">
              {typeof value === 'boolean'
                ? t(value ? 'common.yes' : 'common.no')
                : t(`cards.opt.${String(value)}`, String(value))}
            </MonoText>
          </div>
        ),
      )}

      {msg.text && (
        <p className="mt-2 text-xs font-body text-navy/60 whitespace-pre-wrap">
          {msg.text}
        </p>
      )}

      {msg.attachments.length > 0 && (
        <div className="mt-2 flex gap-2 flex-wrap">
          {msg.attachments.map((a) =>
            a.url ? (
              <img
                key={a.id}
                src={a.url}
                alt={a.kind}
                className="h-16 w-16 object-cover rounded-lg border border-navy/10"
              />
            ) : null,
          )}
        </div>
      )}

      {error && <p className="mt-2 text-xs font-body text-danger">{error}</p>}

      {needsPhoto && mine && (
        <div className="mt-3">
          <p className="text-xs font-body text-amber mb-1">
            {t('cards.photoRequired')}
          </p>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) void attach(f)
            }}
            className="text-xs font-body"
          />
        </div>
      )}

      {needsPhoto && !mine && (
        <p className="mt-3 text-xs font-body text-navy/40">
          {t('cards.awaitingPhoto')}
        </p>
      )}

      {awaitingMe && (
        <div className="mt-3 flex gap-2">
          <button
            disabled={busy}
            onClick={() => answer('accepted')}
            className="px-4 py-2 rounded-lg bg-amber text-navy text-sm font-body disabled:opacity-50"
          >
            {busy ? '...' : t('cards.accept')}
          </button>
          <button
            disabled={busy}
            onClick={() => answer('declined')}
            className="px-4 py-2 rounded-lg border border-navy/15 text-sm font-body disabled:opacity-50"
          >
            {t('cards.decline')}
          </button>
        </div>
      )}

      {awaitingThem && (
        <p className="mt-3 text-xs font-body text-navy/40">{t('cards.awaitingOther')}</p>
      )}
    </div>
  )
}
