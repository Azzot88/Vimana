import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { raiseCard, raiseCardWithFiles } from '../api/terms'
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
  /* The evidence for the declaration being made. Several, because a parcel has
     sides and a closed box proves only that a box existed (owner, 2026-09-12);
     and held here until the whole act goes at once, because the server writes
     nothing until every one of them is accepted. */
  const [files, setFiles] = useState<File[]>([])

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
    setFiles([])
    setOpen(spec)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!open) return
    /* T3.11.27 — the declaration and its evidence are one act (owner, walking
       the flow 2026-09-12, twice).

       First round: «фото должно отправляться вместе со статусом». The
       photograph is not an attachment to the conversation, it is the
       **evidence for this declaration** — `handoff.declared` carries
       `requires_attachment` and the server refuses to let the other side
       confirm a declaration with no photo. Uploading it as a separate chat
       message left the card permanently unconfirmable, with the picture three
       lines above it.

       Second round: «без фото карточка в чат добавляться не должна». Raising
       the card and then uploading was still two requests, so a refused upload —
       wrong type, too large, bytes that do not decode — left exactly the card
       this was meant to prevent, in a chain that cannot take it back. One
       request now: the server validates every file first and writes nothing
       until they are all accepted. */
    if (open.needsPhoto && files.length === 0) {
      setError(t('cards.photoNeeded') as string)
      return
    }
    setBusy(true)
    setError('')
    try {
      const payload = buildPayload(open, values)
      if (open.needsPhoto) {
        await raiseCardWithFiles(
          dealId,
          open.kind,
          files,
          payload,
          note || undefined,
        )
      } else {
        await raiseCard(dealId, open.kind, payload, note || undefined)
      }
      setOpen(null)
      setFiles([])
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
        <div className="mt-2">
          {/* The photograph is part of the declaration, so it is asked for
              **here**, inside the form that makes it — not afterwards, in the
              chat, where it used to land on a row of its own and leave the card
              waiting for evidence it already had.

              T3.11.27 (owner, 2026-09-12): «Основное это фотография… надо
              открыть посылку и снять содержимое… нужна возможность добавить
              несколько фото.» The instruction sits above the input because it
              is about what to photograph, not about which file to pick, and it
              is the one thing on this form that an arbiter will later wish
              somebody had read. */}
          <p className="text-xs font-body text-navy/60 mb-1">
            {t(`cards.shoot.${open.kind.replace('.', '_')}`, {
              defaultValue: t('cards.shoot.default') as string,
            })}
          </p>
          <label className="block">
            <span className="block text-xs font-body text-navy/40 mb-1">
              {t(`chat.kind.${open.needsPhoto}`)}
            </span>
            <input
              type="file"
              multiple
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              className="text-xs font-body"
            />
          </label>
          {files.length > 0 && (
            <p className="mt-1 text-[11px] font-body text-navy/40">
              {t('terms.photosChosen', { count: files.length })}
            </p>
          )}
          <span className="block text-[11px] font-body text-navy/40 mt-1">
            {t('cards.photoWithIt')}
          </span>
        </div>
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
