/** T3.36–T3.39 — what each card asks for, declared once.
 *
 *  This mirrors `PAYLOAD_MODELS` on the server deliberately. Ten hand-written
 *  forms would drift from the ten pydantic models within a release; a field
 *  list next to the kind is something a reviewer can compare line by line.
 *
 *  Labels and option names are i18n keys, not text: `cards.field.<name>` and
 *  `cards.opt.<value>`.
 */
export type DealRole = 'sender' | 'carrier' | 'recipient'

export type CardField =
  | { name: string; type: 'text' | 'number' | 'datetime'; required?: boolean }
  | { name: string; type: 'bool'; default?: boolean }
  | { name: string; type: 'select'; options: readonly string[]; required?: boolean }

export interface CardFormSpec {
  kind: string
  roles: DealRole[]
  fields: CardField[]
  /** Attachment the card cannot be confirmed without (checked server-side). */
  /** T3.11.17 — `pre_seal_photo` joined when the postal stretch did: the parcel
   *  photographed before it was sealed is the evidence that stretch stands on. */
  needsPhoto?: 'handoff_photo' | 'receipt_photo' | 'pre_seal_photo'
  /** T3.12.07 — evidence the card takes if there is any, and does not wait for:
   *  the photo of a handover in hand, the screenshot of a remote transfer. */
  optionalPhoto?: 'receipt_photo' | 'payment_receipt'
  /** T_UX.28 п.4 — the card also takes a selfie, filed under its own kind.
   *  Separate from `optionalPhoto` because it travels **beside** the required
   *  photographs rather than instead of them: «селфи с отправителем, фото
   *  передачи» are two answers, and an arbiter reads the labels. */
  optionalSelfie?: boolean
  /** Whether a free-text note is offered. It travels encrypted, not in payload. */
  hasText?: boolean
}

/** T3.11.22 — the one client-side copy of the vocabulary.
 *
 *  It was written out here **and** in `pages/NewTripPage`, mirroring the same
 *  duplication the backend had between `schemas/cards` and
 *  `schemas/marketplace`. Four literal lists obliged to agree forever: the trip
 *  form offering a method, the deal card executing it, and nothing connecting
 *  any of them. The place a drift shows up is the worst one — a card unable to
 *  name the method the trip was published with, at the moment the parcel
 *  changes hands.
 *
 *  Labels stay in `cards.opt.*` for the same reason: one vocabulary, named once.
 */
export const HANDOVER_METHODS = [
  'in_person',
  'local_post',
  'courier',
  'parcel_locker',
  'poste_restante',
] as const

/** T3.11.27 — the settlement vocabulary, the same three words on the trip, in
 *  the agreement and on the money cards (owner, 2026-09-08: «Опция расчета три»).
 *
 *  It is `trips.PAYMENT_MODELS` said once more rather than imported from there
 *  on purpose: that list is what a **carrier publishes**, this is what a **deal
 *  settles by**, and they are equal today by decision rather than by nature —
 *  the labels already live apart (`trips.paymentModel.*` and `cards.opt.*`).
 *  The mirror the server keeps is `schemas/cards.PaymentMethod`, and that is
 *  the pair a reviewer compares. */
export const PAYMENT_METHODS = [
  'cash_on_delivery',
  'emoney_on_delivery',
  'platform_wallet',
] as const

/** T_UX.29 п.2 — the journey's own order (owner, 2026-09-20).
 *
 *  «Если посылка уже отправлена и летит, то нельзя выбрать статус "Вылетела",
 *  она уже вылетела. И так со всеми статусами — на карточке не должно быть
 *  возможности выбрать предыдущий статус, только один из последующих. Это
 *  должно читаться на карточке.»
 *
 *  Three of the six statuses happen once and in this order. The other three —
 *  `delayed`, `customs`, `storage` — are conditions rather than milestones: a
 *  flight can be delayed twice and a parcel can wait for a connection and then
 *  again for a recipient, so they carry no rank and stay offered throughout.
 *
 *  Read by `CardActions`, which draws the passed ones as a record and offers
 *  only what is still ahead. */
export const TRANSIT_SEQUENCE = ['departed', 'layover', 'arrived'] as const

/** How far along the journey these declarations put the parcel: `-1` for the
 *  statuses that have no place in the order.
 *
 *  Called by: `components/CardActions`, `transitReached`. */
export const transitRank = (stage: string): number =>
  (TRANSIT_SEQUENCE as readonly string[]).indexOf(stage)

/** The furthest milestone already declared, or `-1` for a parcel that has not
 *  reported anything yet.
 *
 *  Called by: `transitOffer`. */
export const transitReached = (declared: readonly string[]): number =>
  declared.reduce((far, s) => Math.max(far, transitRank(s)), -1)

/** T_UX.29 pt.5 (owner, 2026-09-20): «Прошедшие статусы, которые были
 *  кнопками, должны пропадать из блока. А показываться только тот, который
 *  следует сразу после.»
 *
 *  The chips stopped being a menu of the journey and became the next step. What
 *  is behind is gone — the record of it is the chat, where the card itself
 *  stands with its time — and what is ahead is one thing, except in the air:
 *  `layover` repeats and `arrived` follows it, so between departure and landing
 *  the carrier is offered both. Naming only one of them would make a journey
 *  with a connection undeclarable, and a journey without one unfinishable.
 *
 *  `storage` — «Готово к вручению» since this round — is the far end and stays
 *  offered: it is the one status the carrier may need to repeat while a
 *  recipient is found. Delay and customs are gone from the list entirely
 *  (owner: «это будет сказано в чате, если нужно»); old deals keep theirs, and
 *  the labels stay so an arbiter can read them.
 *
 *  Called by: `components/CardActions`. */
export function transitOffer(declared: readonly string[]): string[] {
  const reached = transitReached(declared)
  if (reached < transitRank('departed')) return ['departed']
  if (reached < transitRank('arrived')) return ['layover', 'arrived']
  return ['storage']
}

const MEETING_FIELDS: CardField[] = [
  { name: 'method', type: 'select', options: HANDOVER_METHODS, required: true },
  { name: 'city', type: 'text' },
  { name: 'at', type: 'datetime' },
  { name: 'window_minutes', type: 'number' },
  { name: 'tracking_number', type: 'text' },
  // T3.11.22 — beside the number, never instead of it: a tracking code without
  // the company that issued it is a string nobody can follow. The server
  // refuses it on a hand-to-hand meeting, where nothing was posted.
  { name: 'postal_service', type: 'text' },
]

export const CARD_FORMS: CardFormSpec[] = [
  {
    kind: 'handover.conditions',
    roles: ['sender', 'carrier'],
    fields: [
      { name: 'packaging', type: 'text' },
      { name: 'open_on_handover', type: 'bool' },
      { name: 'photo_required', type: 'bool', default: true },
      { name: 'fragile', type: 'bool' },
    ],
  },
  { kind: 'pickup.proposed', roles: ['sender', 'carrier'], fields: MEETING_FIELDS },
  {
    kind: 'dropoff.proposed',
    roles: ['sender', 'carrier', 'recipient'],
    fields: MEETING_FIELDS,
  },
  {
    /* T3.11.27 (owner, 2026-09-12): «Количество мест сколько передано надо
       убрать. Основное это фотография.»

       A number somebody types about their own parcel proves nothing an arbiter
       can use, and it asked for an answer at the one moment both people are
       standing in a doorway with one hand free. The photographs are the record:
       they show how many things there are, what they look like, and what is
       inside once the parcel is opened. The server still accepts the field for
       the cards that already carry it — history is not rewritten — it is simply
       no longer asked for. */
    /* T_UX.28 п.5 (owner, 2026-09-19) — **one** card for the handover.
       «Фотографии передачи делает любой участник и добавляет в чат, второй
       участник независимо от роли просто соглашается. Если фото добавил один
       из участников, дублировать тот же функционал у второго не нужно.»

       It used to be two — «Передал» and «Получил» — and both asked for a
       photograph of the same handover, so two people photographed one event
       and each confirmed the other's picture of it. */
    kind: 'handoff.declared',
    roles: ['sender', 'carrier'],
    fields: [],
    needsPhoto: 'handoff_photo',
    /* T_UX.28 п.4 — «селфи с отправителем»: its own kind of evidence, asked
       for beside the parcel photographs and never instead of them. */
    optionalSelfie: true,
    hasText: true,
  },
  {
    kind: 'transit.update',
    roles: ['carrier'],
    fields: [
      {
        /* T_DEAL.1 — `storage` joined the four (owner, 2026-09-20): «посылка
           прилетела и не может быть вручена, или ожидает стыковочного рейса».
           A state of the journey, not a rung of the ladder — it can come round
           twice, before the carriage and before the delivery. */
        /* T_UX.28 п.6 — `layover` is on the list here too, and not only in the
           backend's `TransitUpdate`: the chip that cannot be offered is the
           step the carrier cannot declare. Which of them may be pressed is
           decided in `CardActions`, off the stages already declared. */
        name: 'stage',
        type: 'select',
        /* T_UX.29 pt.5 — `delayed` and `customs` are off the list (owner,
           2026-09-20). Which of the rest may be pressed is `transitOffer`; this
           is only what the card can carry at all, and it mirrors the server's
           `TransitUpdate.stage`. */
        options: ['departed', 'layover', 'arrived', 'storage'],
        required: true,
      },
      { name: 'eta', type: 'datetime' },
    ],
    hasText: true,
  },
  {
    /* T_DEAL.1 — the storage bill (owner, 2026-09-20): «у перевозчика есть
       возможность добавить в сделку количество суток хранения по факту,
       отличающееся от счётчика. Счётчик уведомительный, и сумма за хранение
       может быть изменена.»

       So the days are typed rather than taken from the meter, and the other
       side answers: this is money, and a charge the payer cannot refuse would
       make the seller the author of the buyer's bill. */
    kind: 'storage.charged',
    roles: ['carrier'],
    fields: [
      { name: 'days', type: 'number', required: true },
      { name: 'amount', type: 'number' },
      { name: 'currency', type: 'text' },
    ],
    hasText: true,
  },
  {
    /* T3.11.17 — «сдано в почту». The photo is taken **before sealing**: that
       is the one moment the contents are visible and already packed, and the
       tracking code is what ends the carrier's part (`USERJOURNEY` Этап 4a). */
    kind: 'posted.declared',
    roles: ['carrier'],
    fields: [
      { name: 'postal_service', type: 'text', required: true },
      { name: 'tracking_number', type: 'text', required: true },
      /* T3.12.08 — what the post office accepted, so the other side compares it
         with the cargo before confirming. Optional (owner, 2026-09-14). */
      { name: 'postage_cost', type: 'number' },
      { name: 'postage_currency', type: 'text' },
      { name: 'weight_kg', type: 'number' },
      { name: 'length_cm', type: 'number' },
      { name: 'width_cm', type: 'number' },
      { name: 'height_cm', type: 'number' },
    ],
    needsPhoto: 'pre_seal_photo',
    hasText: true,
  },
  {
    /* T3.12.07 — the handover in hand is one act in two directions: either side
       declares, the other confirms, and the photo is welcome but not required
       (owner, 2026-09-13). The sender is offered it only when they are the one
       at the door — `DealStages` narrows that, the server refuses otherwise. */
    kind: 'delivery.declared',
    roles: ['sender', 'carrier', 'recipient'],
    fields: [
      { name: 'method', type: 'select', options: HANDOVER_METHODS, required: true },
    ],
    optionalPhoto: 'receipt_photo',
    hasText: true,
  },
  {
    /* T3.12.08 — «получено как должно» ends a posted deal. The receiving side's
       word, answered by nobody (owner, 2026-09-14); the sender raises it only
       when there is no separate recipient — `DealStages` narrows that. */
    kind: 'received.as_expected',
    roles: ['recipient', 'sender'],
    fields: [],
    hasText: true,
  },
  {
    kind: 'payment.method_agreed',
    roles: ['sender', 'carrier'],
    fields: [
      {
        name: 'method',
        type: 'select',
        options: [...PAYMENT_METHODS],
        required: true,
      },
    ],
  },
  {
    kind: 'payment.declared',
    /* T3.11.27 — whoever the agreement says pays. The recipient is on this list
       because a deal can be «получатель платит на месте», and the server reads
       `payer` from the agreed card and refuses anybody else (403). The screen
       narrows it further by that same field: see `DealStages`, which drops this
       kind for the party who owes nothing rather than offering them a button
       that only ever returns a refusal. */
    roles: ['sender', 'recipient'],
    fields: [
      { name: 'amount', type: 'number', required: true },
      { name: 'currency', type: 'text' },
      {
        name: 'method',
        type: 'select',
        options: [...PAYMENT_METHODS],
        required: true,
      },
    ],
    // T3.12.07 — a sender paying from afar attaches the transfer's screenshot.
    optionalPhoto: 'payment_receipt',
    hasText: true,
  },
  {
    kind: 'issue.reported',
    roles: ['sender', 'carrier', 'recipient'],
    fields: [
      {
        name: 'category',
        type: 'select',
        options: ['delay', 'damage', 'unreachable', 'mismatch'],
        required: true,
      },
    ],
    hasText: true,
  },
  {
    kind: 'cancel.requested',
    roles: ['sender', 'carrier'],
    fields: [
      {
        name: 'costs_borne_by',
        type: 'select',
        options: ['none', 'sender', 'carrier', 'split'],
        required: true,
      },
    ],
    hasText: true,
  },
]

/** i18next splits keys on `.`, so `cards.kind.issue.reported` would look for a
 *  four-level path that does not exist and silently fall back to the raw kind.
 *  The label key uses underscores; this is the one place that knows it. */
export const kindKey = (kind: string): string =>
  `cards.kind.${kind.replace(/\./g, '_')}`

export const formsForRole = (role: DealRole | null): CardFormSpec[] =>
  role ? CARD_FORMS.filter((f) => f.roles.includes(role)) : []

export const specForKind = (kind: string): CardFormSpec | undefined =>
  CARD_FORMS.find((f) => f.kind === kind)

/** Empty optional values are dropped rather than sent as `""` or `NaN`, so the
 *  server's defaults apply instead of a value nobody typed. */
export function buildPayload(
  spec: CardFormSpec,
  values: Record<string, string | boolean>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const field of spec.fields) {
    const raw = values[field.name]
    if (field.type === 'bool') {
      out[field.name] = Boolean(raw)
      continue
    }
    if (raw === undefined || raw === '' || raw === null) continue
    if (field.type === 'number') {
      const n = Number(raw)
      if (!Number.isNaN(n)) out[field.name] = n
      continue
    }
    if (field.type === 'datetime') {
      const d = new Date(String(raw))
      if (!Number.isNaN(d.getTime())) out[field.name] = d.toISOString()
      continue
    }
    out[field.name] = raw
  }
  return out
}
