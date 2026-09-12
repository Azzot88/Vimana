import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { raiseCard } from '../api/terms'
import { uploadAttachment } from '../api/dealvault'
import {
  buildPayload,
  formsForRole,
  kindKey,
  type CardField,
  type CardFormSpec,
  type DealRole,
} from '../lib/cardForms'

/** T3.36–T3.39 — raising a card.
 *
 *  Only what this role may actually raise is offered. Showing every card and
 *  letting the server refuse would teach people that half the buttons here do
 *  not work, which is how a control surface stops being read at all.
 */
interface Props {
  dealId: string
  myRole: DealRole | null
  onDone: () => void
  /** T3.11.17 — the card kinds this stage offers, in the order they happen.
   *  Role still decides who may raise each one; the stage decides when it is
   *  worth offering at all. Omitted means «everything this role may raise»,
   *  which is what the screen did before the ladder existed. */
  only?: string[]
  /** Drawn quieter: the «ещё» row holds a problem and a cancellation, which are
   *  needed when something has gone wrong and should not compete with the step
   *  somebody is trying to take. */
  muted?: boolean
}

export default function CardActions({
  dealId,
  myRole,
  onDone,
  only,
  muted = false,
}: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState<CardFormSpec | null>(null)
  const [values, setValues] = useState<Record<string, string | boolean>>({})
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  /* The evidence for the declaration being made, held until the card exists to
     hang it on. */
  const [file, setFile] = useState<File | null>(null)

  /* Ordered by the stage, not by the catalogue: `only` lists the kinds in the
     order they are meant to happen, and a row of buttons in protocol order
     reads as a sequence rather than as a menu. */
  const byRole = formsForRole(myRole)
  const available = only
    ? only
        .map((kind) => byRole.find((f) => f.kind === kind))
        .filter((f): f is CardFormSpec => Boolean(f))
    : byRole
  if (available.length === 0) return null

  const start = (spec: CardFormSpec) => {
    const initial: Record<string, string | boolean> = {}
    for (const f of spec.fields) {
      if (f.type === 'bool') initial[f.name] = f.default ?? false
    }
    setValues(initial)
    setNote('')
    setError('')
    setFile(null)
    setOpen(spec)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!open) return
    /* T3.11.27 — «фото должно отправляться вместе со статусом» (owner, walking
       the flow 2026-09-12).
    
       The photograph is not an attachment to the conversation, it is the
       **evidence for this declaration**: `handoff.declared` carries
       `requires_attachment` and the server refuses to let the other side
       confirm a declaration with no photo (422). Uploading it as a separate
       chat message therefore left the card permanently unconfirmable — the
       carrier saw «ждём фото» beside a photo that was right there, three lines
       up, hanging off a different row. That is the chain behind «после передачи
       не в пути» and «статус не сменился ни у кого».
    
       So the two happen in one act: raise the card, attach to **it**. Refused
       before either half runs when the picture is missing, rather than leaving
       a declaration nobody can answer. */
    if (open.needsPhoto && !file) {
      setError(t('cards.photoNeeded') as string)
      return
    }
    setBusy(true)
    setError('')
    try {
      const card = await raiseCard(
        dealId,
        open.kind,
        buildPayload(open, values),
        note || undefined,
      )
      if (open.needsPhoto && file) {
        // Same request cycle, from the person's point of view: if this throws,
        // the card exists without its evidence and the error says so — which is
        // recoverable from the card itself, where the upload also lives.
        await uploadAttachment(dealId, card.id, file, open.needsPhoto)
      }
      setOpen(null)
      setFile(null)
      onDone()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('cards.raiseFailed'))
    } finally {
      setBusy(false)
    }
  }


  const field = (f: CardField) => {
    const label = t(`cards.field.${f.name}`, f.name)
    if (f.type === 'bool') {
      return (
        <label key={f.name} className="flex items-center gap-2 text-sm font-body">
          <input
            type="checkbox"
            checked={Boolean(values[f.name])}
            onChange={(e) =>
              setValues((v) => ({ ...v, [f.name]: e.target.checked }))
            }
          />
          {label}
        </label>
      )
    }
    if (f.type === 'select') {
      return (
        <label key={f.name} className="flex-1 min-w-[9rem]">
          <span className="block text-xs font-body text-navy/40 mb-1">{label}</span>
          <select
            required={f.required}
            value={String(values[f.name] ?? '')}
            onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
            className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm"
          >
            <option value="">—</option>
            {f.options.map((o) => (
              <option key={o} value={o}>
                {t(`cards.opt.${o}`, o)}
              </option>
            ))}
          </select>
        </label>
      )
    }
    return (
      <label key={f.name} className="flex-1 min-w-[9rem]">
        <span className="block text-xs font-body text-navy/40 mb-1">{label}</span>
        <input
          type={f.type === 'datetime' ? 'datetime-local' : f.type}
          step={f.type === 'number' ? 'any' : undefined}
          required={f.required}
          value={String(values[f.name] ?? '')}
          onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
          className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm"
        />
      </label>
    )
  }

  if (!open) {
    return (
      <div className="flex flex-wrap gap-2">
        {available.map((spec) => (
          <button
            key={spec.kind}
            type="button"
            onClick={() => start(spec)}
            className={
              muted
                ? 'px-3 py-1.5 rounded-full text-xs font-body text-navy/40 hover:text-amber'
                : 'px-3 py-2 rounded-field border border-navy/15 text-sm font-body text-navy/80 hover:border-cyan hover:text-cyan'
            }
          >
            {t(kindKey(spec.kind), spec.kind)}
          </button>
        ))}
      </div>
    )
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-navy/10 bg-surface p-4 mb-3"
    >
      <p className="text-sm font-display font-semibold text-navy mb-3">
        {t(kindKey(open.kind), open.kind)}
      </p>
      <div className="flex flex-wrap gap-3">{open.fields.map(field)}</div>

      {open.hasText && (
        <label className="block mt-3">
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('cards.note')}
          </span>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm"
          />
        </label>
      )}

      {open.needsPhoto && (
        <label className="mt-2 block">
          {/* The photograph is part of the declaration, so it is asked for
              **here**, inside the form that makes it — not afterwards, in the
              chat, where it used to land on a row of its own and leave the card
              waiting for evidence it already had. */}
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t(`chat.kind.${open.needsPhoto}`)}
          </span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-xs font-body"
          />
          <span className="block text-[11px] font-body text-navy/40 mt-1">
            {t('cards.photoWithIt')}
          </span>
        </label>
      )}

      {error && <p className="mt-2 text-xs font-body text-danger">{error}</p>}

      <div className="mt-3 flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="px-4 py-2 rounded-lg bg-navy text-white text-sm font-body disabled:opacity-50"
        >
          {busy ? '...' : t('cards.send')}
        </button>
        <button
          type="button"
          onClick={() => setOpen(null)}
          className="px-4 py-2 rounded-lg border border-navy/15 text-sm font-body"
        >
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )
}
