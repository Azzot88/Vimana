import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { proposeTerms, takeEditHold, type TermsPayload } from '../api/terms'
import { HANDOVER_METHODS, PAYMENT_METHODS } from '../lib/cardForms'
import type { DealDetail } from '../api/deals'
import type { DealRole } from '../lib/cardForms'
import { usePrefs } from '../hooks/usePrefs'
import { toLocalInput } from '../lib/format'
import DateTimeField from './DateTimeField'
import RecipientModal from './RecipientModal'

/** T3.11.27 — the agreement, in the sections the two sides negotiate.
 *
 *  This used to be three numbers, because the carrier's baseline lived on the
 *  trip and this was only the place to name a different price. The owner's
 *  model 2026-09-07 made it the deal card: handover, delivery and payment, one
 *  form, «Редактировать» and «Подтвердить».
 *
 *  T3.12.04 — **the cargo is shown, not asked.** It was written once at the
 *  response (`D-CARGO-MODEL`); a weight or «хрупкое» typed here would be a
 *  second copy of the parcel two people could edit, and the server refuses it
 *  by name. The price box opens on the carrier's rate times the cargo's weight.
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
  /** T3.11.27 — the deal as the response left it: the cargo to show, the
   *  carrier's rate and methods, and the first version's defaults. An existing
   *  version is always the sharper answer for anything negotiable. */
  fromBoard?: DealDetail | null
  supersedesId?: string | null
  myRole: DealRole | null
  onDone: () => void
}

/** What the response already answered about the terms themselves. */
function boardDefaults(deal: DealDetail | null | undefined): TermsPayload {
  if (!deal) return {}
  // Deliberately not the route. `origin`/`destination` are airport codes, and
  // «DXB» in a field that wants «Dubai Mall, вход у фонтана» is worse than an
  // empty one: it looks answered.
  return {
    currency: deal.currency,
    deadline: deal.deadline ?? null,
  }
}

const SECTIONS = ['handover', 'delivery', 'payment'] as const

export default function TermsProposeForm({
  dealId,
  current,
  fromBoard,
  supersedesId,
  myRole,
  onDone,
}: Props) {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const p = current ?? boardDefaults(fromBoard)
  const str = (v: unknown) => (v === null || v === undefined ? '' : String(v))
  /* A suggestion, not a value: the carrier's own rate times the cargo's weight.
     It fills the price box on the first version and never afterwards — the price
     is what the two of them agree, and a number the screen keeps re-deriving
     would quietly undo an agreed one. */
  const suggested = (() => {
    const rate = fromBoard?.trip_price_per_kg
    const kilos = fromBoard?.cargo_weight_kg
    if (current || !rate || !kilos) return ''
    return String(Math.round(rate * kilos * 100) / 100)
  })()
  const [price, setPrice] = useState(str(p.price_total) || suggested)
  const [handoverMethod, setHandoverMethod] = useState(str(p.handover_method))
  const [handoverPlace, setHandoverPlace] = useState(str(p.handover_place))
  const [deliveryMethod, setDeliveryMethod] = useState(str(p.delivery_method))
  const [deliveryPlace, setDeliveryPlace] = useState(str(p.delivery_place))
  /* T_UX.29 pt.7 п.1 (owner, 2026-09-20): «Там же должна быть возможность
     выбрать время, если встреча личная, передача лично в руки.» The agreement
     has carried `handover_at` and `delivery_at` since T3.11.27 and the form
     simply never asked, so the only way to name a time was a meeting card
     raised afterwards — a second step for something the two of them were
     agreeing anyway. Asked per end and only for a meeting in person: there is
     no hour to agree with a post office. */
  const [handoverAt, setHandoverAt] = useState(toLocalInput(p.handover_at))
  const [deliveryAt, setDeliveryAt] = useState(toLocalInput(p.delivery_at))
  const [payer, setPayer] = useState<'sender' | 'recipient'>(p.payer ?? 'sender')
  /* T_UX.29 pt.7 п.1 — «Когда отправитель предлагает условия перевозчику, ему
     там же нужно выбрать Получателя, в том же окне.»
     `IMPLEMENTATIONPLAN §3.12.3` already requires a recipient **before** the
     terms are fixed, and the server refuses to agree them without one (409). So
     the old order made somebody fill the whole form and meet a refusal at the
     end; the answer belongs where the question is asked. */
  const [recipientOpen, setRecipientOpen] = useState(false)
  const [recipientName, setRecipientName] = useState<string | null>(
    fromBoard?.recipient_name ?? null,
  )
  const [locked, setLocked] = useState<string[]>(p.locked ?? [])
  /* T3.11.27 (owner, 2026-09-12): «Способ оплаты… должен быть внутри формы
     Предложить условия». Opened on the trip's published model, because that is
     the carrier's own answer to this exact question and retyping it is how the
     two records start to differ. */
  const [paymentMethod, setPaymentMethod] = useState(
    p.payment_method ?? fromBoard?.trip_payment_model ?? '',
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  /* T3.11.27 — «После выбора условий должно показываться окно предпросмотра
     перед отправкой в чат… модальное окно с кнопками Предложить условия
     перевозчику и Вернуться к редактированию». The preview is the same card the
     carrier will read, and the way back is a button rather than a correction
     sent after. */
  const [review, setReview] = useState(false)

  const lockedForMe = (section: string) =>
    myRole !== 'carrier' && locked.includes(section)

  /* «Отправить» no longer sends. It asks the browser to validate the required
     fields — that is why it is still a submit — and then opens the preview. The
     request itself is one press further on, in `send`. */
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    /* T_UX.29 pt.7 п.1 — the recipient picker lives inside this form, and it
       has a search box: Enter in it would otherwise submit the terms and open
       the preview over the modal. The picker is not a step of the form, so
       while it is open the form has nothing to submit. */
    if (recipientOpen) return
    setError('')
    setReview(true)
  }

  const send = async () => {
    setBusy(true)
    setError('')
    try {
      /* The window is taken before the change, not after it: while it is open
         the other side neither edits nor confirms, so what they read next is a
         finished version. */
      await takeEditHold(dealId)
      await proposeTerms(dealId, {
        price_total: Number(price),
        handover_method: handoverMethod || null,
        handover_place: handoverPlace || null,
        handover_at: handoverAt ? new Date(handoverAt).toISOString() : null,
        delivery_method: deliveryMethod || null,
        delivery_place: deliveryPlace || null,
        delivery_at: deliveryAt ? new Date(deliveryAt).toISOString() : null,
        payment_method: paymentMethod || undefined,
        payer,
        locked,
        description: null,
        supersedes_id: supersedesId ?? null,
      })
      onDone()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response
        ?.data?.detail
      setError(typeof detail === 'string' ? detail : t('terms.proposeFailed'))
    } finally {
      setBusy(false)
    }
  }

  /* T_UX.29 pt.7 п.1 — the hour of a meeting in person, with our own picker.
     Drawn only for `in_person`: there is no time to agree with a post office or
     a parcel locker, and a blank box beside them would read as a question the
     two of them had failed to answer. */
  const timeBox = (
    value: string,
    setter: (v: string) => void,
    section: string,
    show: boolean,
  ) =>
    show ? (
      <div className="flex-1 min-w-[10rem]">
        <span className="block text-xs font-body text-navy/40 mb-1">
          {t('agreement.field.at')}
        </span>
        <DateTimeField
          value={value}
          onChange={setter}
          style={prefs.style}
          ariaLabel={t('agreement.field.at') as string}
        />
        {lockedForMe(section) && (
          <span className="block text-[11px] font-body text-navy/40 mt-1">
            {t('agreement.locked')}
          </span>
        )}
      </div>
    ) : null

  const box = (
    label: string,
    value: string,
    setter: (v: string) => void,
    opts: { type?: string; section: string; required?: boolean },
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
     Перевозчик, и это должно указываться при формировании рейса.» The agreement
     offers the methods the carrier published and nothing else. A stated value
     outside the list is still kept as an option: an agreement struck before the
     carrier narrowed their trip must keep rendering what it actually says. */
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

  /* T3.12.04 — the cargo as the response wrote it. Read-only, and in the
     preview too, so the carrier's answer is visibly about this parcel. */
  const cargoRows: { label: string; value: string }[] = fromBoard
    ? [
        { label: t('agreement.field.what'), value: fromBoard.cargo_description ?? '' },
        {
          label: t('agreement.field.weight'),
          value:
            fromBoard.cargo_weight_kg != null ? prefs.weight(fromBoard.cargo_weight_kg) : '',
        },
        {
          label: t('agreement.field.declared'),
          value:
            fromBoard.declared_value != null
              ? `${fromBoard.declared_value} ${fromBoard.currency ?? ''}`.trim()
              : '',
        },
      ].filter((row) => row.value.trim() !== '')
    : []

  /* What the preview shows: every answered field, in the order the sections are
     negotiated. Built from the form's own state rather than from the payload it
     is about to send, so what somebody reads and what leaves the screen cannot
     differ. Empty fields are skipped. */
  const summary: { section: string; label: string; value: string }[] = [
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

  const rows = (items: { label: string; value: string }[]) =>
    items.map((row) => (
      <div key={row.label} className="flex justify-between gap-4 py-0.5">
        <dt className="text-xs font-body text-navy/50">{row.label}</dt>
        <dd className="text-xs font-mono text-navy">{row.value}</dd>
      </div>
    ))

  return (
    <form onSubmit={submit} className="rounded-2xl border border-navy/10 bg-surface p-4">
      <p className="text-sm font-display font-semibold text-navy">
        {supersedesId ? t('terms.counterTitle') : t('terms.proposeTitle')}
      </p>

      {cargoRows.length > 0 && (
        <div data-testid="terms-cargo" className="mt-3">
          <h4 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide">
            {t('agreement.section.cargo')}
          </h4>
          <p className="text-[11px] font-body text-navy/40 mb-1">{t('terms.cargoFixed')}</p>
          <dl>{rows(cargoRows)}</dl>
        </div>
      )}

      {/* T_UX.29 pt.7 п.1 — the recipient, asked where the terms are.
          Only of the sender: the role is theirs to fill (`§3.12.3`), and a
          carrier looking at a button they cannot press learns that half the
          controls here do nothing. */}
      {myRole === 'sender' && (
        <div className="mt-3 rounded-field border border-navy/10 bg-surface p-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <span className="block text-xs font-body text-navy/40">
                {t('agreement.field.recipient')}
              </span>
              <span className="text-sm font-body text-navy">
                {recipientName ?? t('agreement.noRecipient')}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setRecipientOpen(true)}
              className="px-3 py-2 rounded-field border border-navy/15 text-sm font-body text-navy/80 hover:border-cyan hover:text-cyan"
            >
              {recipientName
                ? t('agreement.recipientChange')
                : t('agreement.recipientChoose')}
            </button>
          </div>
          {/* Said before the form is filled, not after it is refused: the
              server will not agree terms without a recipient who accepted. */}
          {!recipientName && (
            <p className="text-[11px] font-body text-navy/50 mt-1">
              {t('agreement.recipientNeeded')}
            </p>
          )}
        </div>
      )}

      {heading(SECTIONS[0])}
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
        {timeBox(
          handoverAt,
          setHandoverAt,
          'handover',
          handoverMethod === 'in_person',
        )}
      </div>

      {heading(SECTIONS[1])}
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
        {timeBox(
          deliveryAt,
          setDeliveryAt,
          'delivery',
          deliveryMethod === 'in_person',
        )}
      </div>

      {heading(SECTIONS[2])}
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
        {/* T3.11.27 — «Способ оплаты» is a field in the form. Required: «Модель
            расчета обязательна, но может быть изменена по обоюдному согласию»
            (owner, 2026-09-08). */}
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

      {/* One message, where the press happened. The refusal comes back from
          `send`, which runs from the preview. */}
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
              {cargoRows.length > 0 && (
                <div>
                  <h4 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide mb-1">
                    {t('agreement.section.cargo')}
                  </h4>
                  {rows(cargoRows)}
                </div>
              )}
              {SECTIONS.map((section) => {
                const sectionRows = summary.filter((row) => row.section === section)
                if (sectionRows.length === 0) return null
                return (
                  <div key={section}>
                    <h4 className="text-[11px] font-display font-semibold text-navy/45 uppercase tracking-wide mb-1">
                      {t(`agreement.section.${section}`)}
                    </h4>
                    {rows(sectionRows)}
                  </div>
                )
              })}
            </dl>

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

      {/* T_UX.29 pt.7 п.1 — the same picker the deal screen opens, not a second
          one (`§9a`). It owns the three ways of naming somebody — a contact, a
          public key, a link for a person who is not here yet — and each of them
          is an **offer** the other side accepts; rebuilding that beside it would
          have been a fourth way to get one of the three subtly wrong. */}
      {recipientOpen && (
        <RecipientModal
          open
          dealId={dealId}
          onClose={() => setRecipientOpen(false)}
          onAttached={(name) => {
            setRecipientName(name)
            setRecipientOpen(false)
          }}
          selfRecipient={Boolean(
            fromBoard?.recipient_id &&
              fromBoard.recipient_id === fromBoard.sender_id,
          )}
          onSelf={() => {
            setRecipientName(t('agreement.recipientSelf'))
            setRecipientOpen(false)
          }}
        />
      )}
    </form>
  )
}
