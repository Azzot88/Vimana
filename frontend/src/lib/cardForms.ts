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
  /** T3.11.17 — `pre_seal_photo` joined when the postal leg did: the parcel
   *  photographed before it was sealed is the evidence that leg stands on. */
  needsPhoto?: 'handoff_photo' | 'receipt_photo' | 'pre_seal_photo'
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
      { name: 'temperature_note', type: 'text' },
    ],
  },
  { kind: 'pickup.proposed', roles: ['sender', 'carrier'], fields: MEETING_FIELDS },
  {
    kind: 'dropoff.proposed',
    roles: ['sender', 'carrier', 'recipient'],
    fields: MEETING_FIELDS,
  },
  {
    kind: 'handoff.declared',
    roles: ['sender'],
    fields: [{ name: 'parcel_count', type: 'number' }],
    needsPhoto: 'handoff_photo',
    hasText: true,
  },
  {
    kind: 'transit.update',
    roles: ['carrier'],
    fields: [
      {
        name: 'stage',
        type: 'select',
        options: ['departed', 'arrived', 'delayed', 'customs'],
        required: true,
      },
      { name: 'eta', type: 'datetime' },
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
    ],
    needsPhoto: 'pre_seal_photo',
    hasText: true,
  },
  {
    kind: 'delivery.declared',
    roles: ['carrier'],
    fields: [
      { name: 'method', type: 'select', options: HANDOVER_METHODS, required: true },
    ],
    needsPhoto: 'receipt_photo',
    hasText: true,
  },
  {
    kind: 'payment.method_agreed',
    roles: ['sender', 'carrier'],
    fields: [
      {
        name: 'method',
        type: 'select',
        options: ['cash', 'platform', 'escrow'],
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
        options: ['cash', 'platform', 'escrow'],
        required: true,
      },
    ],
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
