import { useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ackCard, uploadAttachment, type VaultMessage } from '../api/dealvault'
import { kindKey, specForKind, type DealRole } from '../lib/cardForms'
import { usePrefs } from '../hooks/usePrefs'
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
  /** Open a photograph full-screen. The lightbox belongs to the page — one
   *  overlay for a screen, not one per card. */
  onPreview?: (image: { url: string; alt: string }) => void
}

export default function DealCard({ msg, dealId, myRole, mine, onChanged, onPreview }: Props) {
  const { t } = useTranslation()
  const { dateTime } = usePrefs()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  // Many cards render on one screen; a shared id would point every label at the
  // first card's input.
  const photoId = useId()

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
  // T3.11.27 — a cancellation stops waiting. The server stamps the moment onto
  // the card (the shorter of the two accounts' timeouts, capped by departure);
  // silence past it cancels the deal. Shown as a sentence rather than as one
  // more `key: value` row, because it is the only field on this card that
  // changes what happens if nobody touches the screen.
  const deadline =
    msg.card_state === 'pending' && typeof payload.expires_at === 'string'
      ? (payload.expires_at as string)
      : null

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

      {/* T3.11.27 (owner, 2026-09-12): «нужна дополнительная информация из полей
          что не оставлены пустыми. Заголовки пустых полей не показываем.»

          An empty string is not an answer, and a label with nothing beside it
          reads as a field somebody failed to fill rather than one they were
          never asked about. `buildPayload` already drops empty optionals on the
          way out, but a card can be raised by anything that speaks the API, and
          what is stored is not this component's to assume. */}
      {Object.entries(payload).map(([key, value]) =>
        value === null ||
        value === undefined ||
        typeof value === 'object' ||
        (typeof value === 'string' && !value.trim()) ||
        key === 'expires_at' ? null : (
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

      {/* T3.11.27 — the evidence lives here and nowhere else (owner,
          2026-09-12). The chat used to draw the same photograph a second time
          on its way past the message; it no longer does, so what the card shows
          is all there is — which means it also has to carry the two things the
          loose copy carried: the kind of photograph this is, and the hash that
          puts it in the chain. */}
      {msg.attachments.length > 0 && (
        <div className="mt-2 space-y-1">
          <div className="flex gap-2 flex-wrap">
            {msg.attachments.map((a) =>
              a.url ? (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => onPreview?.({ url: a.url!, alt: t(`chat.kind.${a.kind}`, a.kind) })}
                  className="rounded-lg overflow-hidden border border-navy/10 hover:border-cyan/40 transition-colors cursor-zoom-in"
                  aria-label={t('chat.openFullscreen') as string}
                >
                  <img
                    src={a.url}
                    alt={t(`chat.kind.${a.kind}`, a.kind)}
                    className="h-16 w-16 object-cover block"
                  />
                </button>
              ) : null,
            )}
          </div>
          {msg.attachments.map((a) => (
            <MonoText key={a.id} className="text-[10px] text-navy/25 block">
              {t(`chat.kind.${a.kind}`, a.kind)} · sha256:{a.file_hash.slice(0, 16)}…
            </MonoText>
          ))}
        </div>
      )}

      {error && <p className="mt-2 text-xs font-body text-danger">{error}</p>}

      {needsPhoto && mine && (
        <div className="mt-3">
          <label htmlFor={photoId} className="block text-xs font-body text-amber mb-1">
            {t('cards.photoRequired')}
          </label>
          <input
            id={photoId}
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

      {deadline && (
        <p className="mt-1 text-xs font-body text-navy/45">
          {t('cards.cancelDeadline', { at: dateTime(deadline) })}
        </p>
      )}
    </div>
  )
}
