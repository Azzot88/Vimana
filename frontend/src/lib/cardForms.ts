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
  | { name: string; type: 'select'; options: string[]; required?: boolean }

export interface CardFormSpec {
  kind: string
  roles: DealRole[]
  fields: CardField[]
  /** Attachment the card cannot be confirmed without (checked server-side). */
  needsPhoto?: 'handoff_photo' | 'receipt_photo'
  /** Whether a free-text note is offered. It travels encrypted, not in payload. */
  hasText?: boolean
}

const HANDOVER_METHODS = [
  'in_person',
  'local_post',
  'courier',
  'parcel_locker',
  'poste_restante',
]

const MEETING_FIELDS: CardField[] = [
  { name: 'method', type: 'select', options: HANDOVER_METHODS, required: true },
  { name: 'city', type: 'text' },
  { name: 'at', type: 'datetime' },
  { name: 'window_minutes', type: 'number' },
  { name: 'tracking_number', type: 'text' },
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
    roles: ['sender'],
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
