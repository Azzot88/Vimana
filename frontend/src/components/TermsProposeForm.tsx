import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { proposeTerms, takeEditHold, type TermsPayload } from '../api/terms'
import { HANDOVER_METHODS } from '../lib/cardForms'
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
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

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

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      /* The window is taken before the change, not after it: while it is open
         the other side neither edits nor confirms, so what they read next is a
         finished version. Taken here rather than when the form opens, because a
         form somebody opened and walked away from would hold the deal for two
         minutes over nothing. */
      await takeEditHold(dealId)
      await proposeTerms(dealId, {
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
        payer,
        locked,
        description: description || null,
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

  const methodBox = (
    label: string,
    value: string,
    setter: (v: string) => void,
    section: string,
  ) => (
    <label className="flex-1 min-w-[8rem]">
      <span className="block text-xs font-body text-navy/40 mb-1">{label}</span>
      <select
        value={value}
        disabled={lockedForMe(section)}
        onChange={(e) => setter(e.target.value)}
        className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm disabled:bg-navy/5 disabled:text-navy/40"
      >
        <option value="">—</option>
        {HANDOVER_METHODS.map((m) => (
          <option key={m} value={m}>
            {t(`cards.opt.${m}`, m)}
          </option>
        ))}
      </select>
    </label>
  )

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
      </div>

      <label className="block mt-3">
        <span className="block text-xs font-body text-navy/40 mb-1">
          {t('terms.cargoDescription')}
        </span>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-navy/15 font-body text-sm"
        />
      </label>

      {error && <p className="mt-2 text-xs font-body text-danger">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="mt-3 px-4 py-2 rounded-lg bg-navy text-white text-sm font-body disabled:opacity-50"
      >
        {busy ? '...' : t('terms.send')}
      </button>
    </form>
  )
}
