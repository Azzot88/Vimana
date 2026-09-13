import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { proposeTerms, takeEditHold, type TermsPayload } from '../api/terms'
import { uploadAttachment } from '../api/dealvault'
import { HANDOVER_METHODS, PAYMENT_METHODS } from '../lib/cardForms'
import type { DealDetail } from '../api/deals'
import type { DealRole } from '../lib/cardForms'

/** T3.11.27 — the agreement, in the four sections the two sides negotiate.
 *
 *  This used to be three numbers, because the carrier's baseline lived on the
 *  trip and this was only the place to name a different price. The owner's
 *  model 2026-09-07 made it the deal card: cargo, handover, delivery and
 *  payment, one form, «Редактировать» and «Подтвердить».
 *
 *  **The current version is prefilled.** The API takes the whole card, so a
 *  person moving the meeting place would otherwise have to retype the price to
 *  keep it — and the retyped number is where a deal quietly changes value.
 *
 *  Sections the carrier has locked are drawn read-only for the other side. The
 *  server refuses them by name either way; the form does not pretend they can be
 *  typed into.
 *
 *  Functions (PROJECT §6.2a):
 *  - `TermsProposeForm({ dealId, current, fromBoard, supersedesId, myRole,
 *    onDone })` — default export. Called by: `components/DealStages`.
 */
interface Props {
  dealId: string
  /** The version being edited, if there is one. */
  current?: TermsPayload | null
  /** T3.11.27 — «Форма на доске остаётся как есть, карточка подставляется
   *  заполненной из неё» (owner, 2026-09-07). Used only when there is nothing
   *  to edit yet: an existing version is always the sharper answer, and letting
   *  the board overwrite it would resurrect numbers two people had moved past. */
  fromBoard?: DealDetail | null
  supersedesId?: string | null
  myRole: DealRole | null
  onDone: () => void
}

/** What the board form already answered. Read once, at the top of the first
 *  version — the sender typed these a minute ago on the way here, and asking
 *  again is how the order and the agreement end up disagreeing about the same
 *  parcel. */
function boardDefaults(deal: DealDetail | null | undefined): TermsPayload {
  if (!deal) return {}
  // Deliberately not the route. `origin`/`destination` are airport codes, and
  // «DXB» in a field that wants «Dubai Mall, вход у фонтана» is worse than an
  // empty one: it looks answered.
  return {
    cargo_what: deal.cargo_description || null,
    declared_value: deal.declared_value,
    currency: deal.currency,
    deadline: deal.order_deadline ?? null,
  }
}

const SECTIONS = ['cargo', 'handover', 'delivery', 'payment'] as const

export default function TermsProposeForm({
  dealId,
  current,
  fromBoard,
  supersedesId,
  myRole,
  onDone,
}: Props) {
  const { t } = useTranslation()
  const p = current ?? boardDefaults(fromBoard)
  const str = (v: unknown) => (v === null || v === undefined ? '' : String(v))
  const [weight, setWeight] = useState(str(p.weight_kg))
  const [price, setPrice] = useState(str(p.price_total))
  const [declared, setDeclared] = useState(str(p.declared_value))
  const [what, setWhat] = useState(str(p.cargo_what))
  const [packaging, setPackaging] = useState(str(p.cargo_packaging))
  const [fragile, setFragile] = useState(Boolean(p.cargo_fragile))
  const [openOnHandover, setOpenOnHandover] = useState(
    Boolean(p.cargo_open_on_handover),
  )
  const [url, setUrl] = useState(str(p.cargo_url))
  const [handoverMethod, setHandoverMethod] = useState(str(p.handover_method))
  const [handoverPlace, setHandoverPlace] = useState(str(p.handover_place))
  const [deliveryMethod, setDeliveryMethod] = useState(str(p.delivery_method))
  const [deliveryPlace, setDeliveryPlace] = useState(str(p.delivery_place))
  const [payer, setPayer] = useState<'sender' | 'recipient'>(p.payer ?? 'sender')
  const [locked, setLocked] = useState<string[]>(p.locked ?? [])
  /* T3.11.27 (owner, 2026-09-12): «Способ оплаты… должен быть внутри формы
     Предложить условия». It was a chip of its own beside the form — a second
     act, raising a second card, about the same agreement. Opened on the trip's
     published model, because that is the carrier's own answer to this exact
     question and retyping it is how the two records start to differ. */
  const [paymentMethod, setPaymentMethod] = useState(
    p.payment_method ?? fromBoard?.trip_payment_model ?? '',
  )
  /* T3.11.27 — «возможность загрузки нескольких фото товара… Прикрепить фото
     отправления». Several, because one photograph of a parcel is a photograph
     of one side of it, and the stage upload that used to live next to this form
     took exactly one and filed it as a separate chat row. They hang on the
     proposal itself now, so the carrier reads the terms and sees the thing. */
  const [photos, setPhotos] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  /* T3.11.27 — «После выбора условий должно показываться окно предпросмотра
     перед отправкой в чат… модальное окно с кнопками Предложить условия
     перевозчику и Вернуться к редактированию».
     The form is long and half of it is optional, so «Отправить» was a press
     into the dark: the proposal reached the other side before its author had
     ever seen it as a whole. The preview is the same card the carrier will
     read, and the way back is a button rather than a correction sent after. */
  const [review, setReview] = useState(false)

  /* A suggestion, not a value: the carrier's own rate times the weight the
     sender is about to type. It fills the price box on the first version and
     never afterwards — the price is what the two of them agree, and a number
     the screen keeps re-deriving would quietly undo an agreed one. */
  const suggestPrice = (kg: string) => {
    const rate = fromBoard?.trip_price_per_kg
    const kilos = Number(kg)
    if (current || !rate || !Number.isFinite(kilos) || kilos <= 0) return
    setPrice(String(Math.round(rate * kilos * 100) / 100))
  }

  const lockedForMe = (section: string) =>
    myRole !== 'carrier' && locked.includes(section)

  /* «Отправить» no longer sends. It asks the browser to validate the required
     fields — that is why it is still a submit — and then opens the preview. The
     request itself is one press further on, in `send`. */
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setReview(true)
  }

  const send = async () => {
    setBusy(true)
    setError('')
    try {
      /* The window is taken before the change, not after it: while it is open
         the other side neither edits nor confirms, so what they read next is a
         finished version. Taken here rather than when the form opens, because a
         form somebody opened and walked away from would hold the deal for two
         minutes over nothing. */
      await takeEditHold(dealId)
      const terms = await proposeTerms(dealId, {
        weight_kg: Number(weight),
        price_total: Number(price),
        declared_value: Number(declared || 0),
        cargo_what: what || null,
        cargo_packaging: packaging || null,
        cargo_fragile: fragile,
        cargo_open_on_handover: openOnHandover,
        cargo_url: url || null,
        handover_method: handoverMethod || null,
        handover_place: handoverPlace || null,
        delivery_method: deliveryMethod || null,
        delivery_place: deliveryPlace || null,
        payment_method: paymentMethod || undefined,
        payer,
        locked,
        description: null,
        supersedes_id: supersedesId ?? null,
      })
      /* After the proposal exists, because they hang on it. Sequential rather
         than parallel: five photographs of one parcel are five upload slots on
         somebody's phone connection, and the order they arrive in is the order
         they were chosen. A failure here leaves the terms standing without
         their pictures — recoverable by editing, and said out loud rather than
         rolled back, since the terms themselves are the thing being agreed. */
      for (const file of photos) {
        await uploadAttachment(dealId, terms.id, file, 'cargo_photo')
      }
      onDone()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('terms.proposeFailed'))
    } finally {
      setBusy(false)
    }
  }

  const box = (
    label: string,
    value: string,
    setter: (v: string) => void,
    opts: { type?: string; section: string; required?: boolean } = {
      section: 'cargo',
    },
  ) => (
    <label className="flex-1 min-w-[8rem]">
      <span className="block text-xs font-body text-navy/40 mb-1">{label}</span>
      <input
        type={opts.type ?? 'text'}
        step={opts.type === 'number' ? 'any' : undefined}
        min={opts.type === 'number' ? '0' : undefined}
        required={opts.required}
        disabled={lockedForMe(opts.section)}
        value={value}
        onChange={(e) => setter(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm disabled:bg-navy/5 disabled:text-navy/40"
      />
    </label>
  )

  /* T3.11.27 (owner, 2026-09-12): «Условия передачи товара в отправку выбирает
     Перевозчик, и это должно указываться при формировании рейса. Для
     Отправителя он указывает как хочет получить посылку.»

     The carrier states both ends when they publish. The agreement then offers
     those and nothing else — the same master rule as the categories, «в заявке
     появляется только то что есть в опубликованом рейсе». Offering a sender
     «постамат» on a trip whose carrier only meets people is offering them a
     refusal.

     A stated value outside the list is still kept as an option: an agreement
     struck before the carrier narrowed their trip must keep rendering what it
     actually says rather than silently showing an empty box. */
  const methodBox = (
    label: string,
    value: string,
    setter: (v: string) => void,
    section: string,
    offered?: string[],
  ) => {
    const allowed =
      offered && offered.length > 0
        ? offered.filter((m) => (HANDOVER_METHODS as readonly string[]).includes(m))
        : [...HANDOVER_METHODS]
    const options = value && !allowed.includes(value) ? [value, ...allowed] : allowed
    return (
      <label className="flex-1 min-w-[8rem]">
        <span className="block text-xs font-body text-navy/40 mb-1">{label}</span>
        <select
          value={value}
          disabled={lockedForMe(section)}
          onChange={(e) => setter(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm disabled:bg-navy/5 disabled:text-navy/40"
        >
          <option value="">—</option>
          {options.map((m) => (
            <option key={m} value={m}>
              {t(`cards.opt.${m}`, m)}
            </option>
          ))}
        </select>
      </label>
    )
  }

  /* What the preview shows: every answered field, in the order the sections are
     negotiated. Built from the form's own state rather than from the payload it
     is about to send, so what somebody reads and what leaves the screen cannot
     differ. Empty fields are skipped — a summary listing «Упаковка: —» teaches
     people to stop reading summaries. */
  const summary: { section: string; label: string; value: string }[] = [
    { section: 'cargo', label: t('agreement.field.what'), value: what },
    { section: 'cargo', label: t('terms.weight'), value: weight },
    { section: 'cargo', label: t('terms.declaredValue'), value: declared },
    { section: 'cargo', label: t('agreement.field.packaging'), value: packaging },
    { section: 'cargo', label: t('agreement.field.url'), value: url },
    {
      section: 'cargo',
      label: t('agreement.field.fragile'),
      value: fragile ? t('common.yes') : '',
    },
    {
      section: 'cargo',
      label: t('agreement.field.openOnHandover'),
      value: openOnHandover ? t('common.yes') : '',
    },
    {
      section: 'handover',
      label: t('agreement.field.method'),
      value: handoverMethod ? t(`cards.opt.${handoverMethod}`, handoverMethod) : '',
    },
    { section: 'handover', label: t('agreement.field.place'), value: handoverPlace },
    {
      section: 'delivery',
      label: t('agreement.field.method'),
      value: deliveryMethod ? t(`cards.opt.${deliveryMethod}`, deliveryMethod) : '',
    },
    { section: 'delivery', label: t('agreement.field.place'), value: deliveryPlace },
    { section: 'payment', label: t('terms.price'), value: price },
    {
      section: 'payment',
      label: t('agreement.field.paymentMethod'),
      value: paymentMethod ? t(`cards.opt.${paymentMethod}`, paymentMethod) : '',
    },
    {
      section: 'payment',
      label: t('agreement.field.payer'),
      value: t(`agreement.payer.${payer}`),
    },
  ].filter((row) => row.value.trim() !== '')

  const heading = (section: string) => (
    <div className="flex items-center gap-2 mt-3 mb-1">
      <h4 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide">
        {t(`agreement.section.${section}`)}
      </h4>
      {/* Only the carrier sets a lock: it is «I carry it this way or not at
          all», and a sender who could lock a section would be dictating the
          terms of somebody else's flight. */}
      {myRole === 'carrier' ? (
        <label className="text-[10px] font-body text-navy/40 flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            checked={locked.includes(section)}
            onChange={(e) =>
              setLocked((prev) =>
                e.target.checked
                  ? [...prev, section]
                  : prev.filter((s) => s !== section),
              )
            }
          />
          🔒 {t('agreement.lockIt')}
        </label>
      ) : (
        locked.includes(section) && (
          <span className="text-[10px] font-mono text-navy/40">
            🔒 {t('agreement.locked')}
          </span>
        )
      )}
    </div>
  )

  return (
    <form onSubmit={submit} className="rounded-2xl border border-navy/10 bg-surface p-4">
      <p className="text-sm font-display font-semibold text-navy">
        {supersedesId ? t('terms.counterTitle') : t('terms.proposeTitle')}
      </p>

      {heading(SECTIONS[0])}
      <div className="flex flex-wrap gap-3">
        {box(t('agreement.field.what'), what, setWhat, { section: 'cargo' })}
        {box(
          t('terms.weight'),
          weight,
          (v) => {
            setWeight(v)
            // T3.11.27 — the price box fills itself from the carrier's rate the
            // first time a weight is typed. Only on the first version, and only
            // while the price is still the form's own suggestion.
            suggestPrice(v)
          },
          { type: 'number', section: 'cargo', required: true },
        )}
        {box(t('terms.declaredValue'), declared, setDeclared, {
          type: 'number',
          section: 'cargo',
        })}
      </div>
      <div className="flex flex-wrap gap-3 mt-2">
        {box(t('agreement.field.packaging'), packaging, setPackaging, {
          section: 'cargo',
        })}
        {box(t('agreement.field.url'), url, setUrl, { section: 'cargo' })}
      </div>
      <div className="flex flex-wrap gap-4 mt-2">
        <label className="flex items-center gap-2 text-xs font-body text-navy/70">
          <input
            type="checkbox"
            checked={fragile}
            disabled={lockedForMe('cargo')}
            onChange={(e) => setFragile(e.target.checked)}
          />
          {t('agreement.field.fragile')}
        </label>
        <label className="flex items-center gap-2 text-xs font-body text-navy/70">
          <input
            type="checkbox"
            checked={openOnHandover}
            disabled={lockedForMe('cargo')}
            onChange={(e) => setOpenOnHandover(e.target.checked)}
          />
          {t('agreement.field.openOnHandover')}
        </label>
      </div>

      {heading(SECTIONS[1])}
      <div className="flex flex-wrap gap-3">
        {methodBox(
          t('agreement.field.method'),
          handoverMethod,
          setHandoverMethod,
          'handover',
          fromBoard?.trip_handover_methods,
        )}
        {box(t('agreement.field.place'), handoverPlace, setHandoverPlace, {
          section: 'handover',
        })}
      </div>

      {heading(SECTIONS[2])}
      <div className="flex flex-wrap gap-3">
        {methodBox(
          t('agreement.field.method'),
          deliveryMethod,
          setDeliveryMethod,
          'delivery',
          fromBoard?.trip_delivery_methods,
        )}
        {box(t('agreement.field.place'), deliveryPlace, setDeliveryPlace, {
          section: 'delivery',
        })}
      </div>

      {heading(SECTIONS[3])}
      <div className="flex flex-wrap gap-3">
        {box(t('terms.price'), price, setPrice, {
          type: 'number',
          section: 'payment',
          required: true,
        })}
        <label className="flex-1 min-w-[8rem]">
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('agreement.field.payer')}
          </span>
          <select
            value={payer}
            disabled={lockedForMe('payment')}
            onChange={(e) => setPayer(e.target.value as 'sender' | 'recipient')}
            className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm disabled:bg-navy/5 disabled:text-navy/40"
          >
            <option value="sender">{t('agreement.payer.sender')}</option>
            <option value="recipient">{t('agreement.payer.recipient')}</option>
          </select>
        </label>
        {/* T3.11.27 — «Способ оплаты» was a chip beside the form and is now a
            field in it. Required: «Модель расчета обязательна, но может быть
            изменена по обоюдному согласию» (owner, 2026-09-08) — the change
            later is the `payment.method_agreed` card, which speaks the same
            three words. */}
        <label className="flex-1 min-w-[9rem]">
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('agreement.field.paymentMethod')}
          </span>
          <select
            value={paymentMethod}
            required
            disabled={lockedForMe('payment')}
            onChange={(e) => setPaymentMethod(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm disabled:bg-navy/5 disabled:text-navy/40"
          >
            <option value="">—</option>
            {PAYMENT_METHODS.map((m) => (
              <option key={m} value={m}>
                {t(`cards.opt.${m}`, m)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* T3.11.27 — «Над кнопкой добавить возможность загрузки нескольких фото
          товара и переименовать Фото товара в Прикрепить фото отправления»
          (owner, 2026-09-12). The second «Что везём» box that used to stand
          here is gone: the cargo section at the top asks that question, and
          asking it twice in one form is how two answers to it get stored. */}
      <div className="mt-3">
        <label className="block">
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('terms.attachPhotos')}
          </span>
          <input
            type="file"
            multiple
            /* T3.11.27 — every picture: what is acceptable is decided by the
               bytes, server-side, not by a list of five types here. */
            accept="image/*"
            onChange={(e) => setPhotos(Array.from(e.target.files ?? []))}
            className="text-xs font-body"
          />
        </label>
        {photos.length > 0 && (
          <p className="mt-1 text-[11px] font-body text-navy/40">
            {t('terms.photosChosen', { count: photos.length })}
          </p>
        )}
      </div>

      {/* One message, where the press happened. The refusal comes back from
          `send`, which runs from the preview — printing it here as well put the
          same sentence twice on one screen, once behind a modal covering it. */}
      {error && !review && (
        <p className="mt-2 text-xs font-body text-danger">{error}</p>
      )}
      <button
        type="submit"
        disabled={busy}
        className="mt-3 px-4 py-2 rounded-lg bg-navy text-white text-sm font-body disabled:opacity-50"
      >
        {busy ? '...' : t('terms.send')}
      </button>

      {/* T3.11.27 — the preview, and then the two buttons the owner named. It
          shows what the other side will read, in their order, with the empty
          fields left out: a summary that lists «Упаковка: —» teaches people to
          stop reading summaries. */}
      {review && (
        <div
          className="fixed inset-0 z-modal bg-navy/50 backdrop-blur-sm flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setReview(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-card p-5 max-w-md w-full max-h-[85vh] overflow-y-auto space-y-3"
          >
            <h3 className="font-display font-semibold text-base text-navy">
              {t('terms.reviewTitle')}
            </h3>
            <p className="text-xs font-body text-navy/50">
              {t('terms.reviewHint')}
            </p>

            <dl className="space-y-2">
              {SECTIONS.map((section) => {
                const rows = summary.filter((row) => row.section === section)
                if (rows.length === 0) return null
                return (
                  <div key={section}>
                    <h4 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide mb-1">
                      {t(`agreement.section.${section}`)}
                    </h4>
                    {rows.map((row) => (
                      <div
                        key={row.label}
                        className="flex justify-between gap-4 py-0.5"
                      >
                        <dt className="text-xs font-body text-navy/50">
                          {row.label}
                        </dt>
                        <dd className="text-xs font-mono text-navy">{row.value}</dd>
                      </div>
                    ))}
                  </div>
                )
              })}
            </dl>

            {photos.length > 0 && (
              <p className="text-xs font-body text-navy/50">
                {t('terms.photosChosen', { count: photos.length })}
              </p>
            )}

            {error && <p className="text-xs font-body text-danger">{error}</p>}

            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                disabled={busy}
                onClick={() => void send()}
                className="px-4 py-2 rounded-lg bg-navy text-white text-sm font-body disabled:opacity-50"
              >
                {busy ? '...' : t('terms.confirmSend')}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setReview(false)}
                className="px-4 py-2 rounded-lg border border-navy/15 text-sm font-body disabled:opacity-50"
              >
                {t('terms.backToEdit')}
              </button>
            </div>
          </div>
        </div>
      )}
    </form>
  )
}
