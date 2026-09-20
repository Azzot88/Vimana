import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { raiseCard, raiseCardWithFiles } from '../api/terms'
import PhotoPicker from './PhotoPicker'
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
  /** T_UX.28 — a caption this stage wants instead of the card's own name, by
   *  kind. «Перенести вручение» is the right words only when there is something
   *  to move; the first time it is «Назначить вручение», and the stage is what
   *  knows which of the two it is (owner, 2026-09-16). */
  labels?: Record<string, string>
}

export default function CardActions({
  dealId,
  myRole,
  onDone,
  only,
  muted = false,
  labels,
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
  /* T_UX.28 п.4 — kept apart from the pile above all the way to the server, so
     it can be filed under its own kind. */
  const [selfies, setSelfies] = useState<File[]>([])

  /* Ordered by the stage, not by the catalogue: `only` lists the kinds in the
     order they are meant to happen, and a row of buttons in protocol order
     reads as a sequence rather than as a menu. */
  const byRole = formsForRole(myRole)
  const available = only
    ? only
        .map((kind) => byRole.find((f) => f.kind === kind))
        .filter((f): f is CardFormSpec => Boolean(f))
    : byRole

  const start = (spec: CardFormSpec) => {
    const initial: Record<string, string | boolean> = {}
    for (const f of spec.fields) {
      if (f.type === 'bool') initial[f.name] = f.default ?? false
    }
    setValues(initial)
    setNote('')
    setError('')
    setFiles([])
    setSelfies([])
    setOpen(spec)
  }

  /* T_UX.28 п.3 (owner, 2026-09-19, вариант А): «Если на стадии у роли ровно
     одно действие — разворачивать его форму сразу, без кнопки. Если несколько —
     разворачивать первое (оно идёт первым по протоколу), остальные оставить
     кнопками. Блок "ещё" остаётся свёрнутым всегда.»

     The button that only opened a form was a press that told nobody anything:
     at a stage with one action it asked the person to confirm they wanted to do
     the thing the stage exists for. `muted` — the «ещё» row, a problem and a
     cancellation — stays folded, because those are not the step anybody came to
     take.

     Opened once per stage, not on every render: `autoOpened` is what lets
     somebody close the form and keep it closed. */
  const firstKind = muted ? null : available[0]?.kind ?? null
  const autoOpened = useRef<string | null>(null)
  useEffect(() => {
    if (!firstKind || autoOpened.current === firstKind) return
    const spec = available.find((f) => f.kind === firstKind)
    if (!spec) return
    autoOpened.current = firstKind
    start(spec)
    // `start` and `available` are rebuilt every render; the kind is what
    // actually changes, and it is what this watches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstKind])

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
      if (
        open.needsPhoto ||
        (open.optionalPhoto && files.length > 0) ||
        selfies.length > 0
      ) {
        await raiseCardWithFiles(
          dealId,
          open.kind,
          files,
          payload,
          note || undefined,
          selfies,
        )
      } else {
        await raiseCard(dealId, open.kind, payload, note || undefined)
      }
      setOpen(null)
      setFiles([])
      setSelfies([])
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

  if (available.length === 0) return null

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
            {labels?.[spec.kind] ?? t(kindKey(spec.kind), spec.kind)}
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
        {labels?.[open.kind] ?? t(kindKey(open.kind), open.kind)}
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

      {(open.needsPhoto || open.optionalPhoto) && (
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
          {/* T_UX.28 п.4 — «нужен красивый выбор нескольких фото» (owner,
              2026-09-19). The bare input showed «3 файла» and replaced the
              whole selection on the next pick, which is the wrong shape for
              photographs taken one at a time from different sides. */}
          <PhotoPicker
            value={files}
            onChange={setFiles}
            label={t(`chat.kind.${open.needsPhoto ?? open.optionalPhoto}`)}
            optional={!open.needsPhoto}
          />
          <span className="block text-[11px] font-body text-navy/40 mt-1">
            {t('cards.photoWithIt')}
          </span>
        </div>
      )}

      {/* T_UX.28 п.4 — «селфи с отправителем». Beside the parcel photographs,
          never instead of them, and filed under its own kind: a picture of the
          parcel says what changed hands, a selfie says who was standing
          there. */}
      {open.optionalSelfie && (
        <div className="mt-3">
          <PhotoPicker
            value={selfies}
            onChange={setSelfies}
            label={t('chat.kind.selfie')}
            hint={t('cards.selfieHint')}
            optional
          />
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

      {/* T_UX.28 п.3, вариант А — «остальные оставить кнопками». The stage's
          first action is open; everything else it offers stays one press away,
          under the form rather than hidden behind it, so switching to another
          action does not start with closing this one. */}
      {available.length > 1 && (
        <div className="mt-3 pt-3 border-t border-navy/5 flex flex-wrap gap-2">
          {available
            .filter((spec) => spec.kind !== open.kind)
            .map((spec) => (
              <button
                key={spec.kind}
                type="button"
                onClick={() => start(spec)}
                className="px-3 py-2 rounded-field border border-navy/15 text-sm font-body text-navy/80 hover:border-cyan hover:text-cyan"
              >
                {labels?.[spec.kind] ?? t(kindKey(spec.kind), spec.kind)}
              </button>
            ))}
        </div>
      )}
    </form>
  )
}
