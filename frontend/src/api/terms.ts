import api from './client'
import type { VaultMessage } from './dealvault'

export interface NormalizedTerms {
  direction: string | null
  route: string
  distance_km: number | null
  weight_kg: number
  chargeable_weight_kg: number
  price_total: number
  currency: string
  price_per_kg: number | null
  price_per_km: number | null
}

export interface TermsPayload {
  weight_kg?: number
  dimensions_cm?: number[] | null
  declared_value?: number
  price_total?: number
  currency?: string
  deadline?: string | null
  payment_method?: string
  normalized?: NormalizedTerms
  below_carrier_minimum?: boolean
  agreed_at?: string
  proposal_id?: string
  platform_params?: Record<string, string>
  // T3.11.27 — the rest of the agreement: one card holds what four used to.
  cargo_what?: string | null
  cargo_packaging?: string | null
  cargo_fragile?: boolean
  cargo_open_on_handover?: boolean
  cargo_url?: string | null
  handover_method?: string | null
  handover_place?: string | null
  handover_at?: string | null
  delivery_method?: string | null
  delivery_place?: string | null
  delivery_at?: string | null
  /** Who pays the carrier — it decides whose button closes the deal. */
  payer?: 'sender' | 'recipient'
  /** Sections the carrier has locked in this deal. */
  locked?: string[]
}

export interface Terms {
  id: string
  deal_id: string
  card_kind: string
  card_state: string
  requires_ack_by: string | null
  supersedes_id: string | null
  payload: TermsPayload
  description: string | null
  created_at: string
}

export interface TermsInput {
  weight_kg: number
  price_total: number
  declared_value: number
  currency?: string
  dimensions_cm?: number[] | null
  deadline?: string | null
  /** T3.11.27 — one of `PAYMENT_METHODS`: the same three words the trip is
   *  published with. Required in practice — the owner's rule 2026-09-08 is
   *  «модель расчёта обязательна» — but optional on the wire so an older client
   *  and the server's own default stay in step. */
  payment_method?: string
  description?: string | null
  supersedes_id?: string | null
  // T3.11.27 — the four sections. Every one optional: a deal born from the
  // board form has a price and a weight and nothing else, and a half-filled
  // agreement is the normal state of the first stage.
  cargo_what?: string | null
  cargo_packaging?: string | null
  cargo_fragile?: boolean
  cargo_open_on_handover?: boolean
  cargo_url?: string | null
  handover_method?: string | null
  handover_place?: string | null
  handover_at?: string | null
  delivery_method?: string | null
  delivery_place?: string | null
  delivery_at?: string | null
  payer?: 'sender' | 'recipient'
  locked?: string[]
}

/** Current contract, or the proposal still awaiting an answer. `null` when
 *  neither exists yet. */
export async function getTerms(dealId: string): Promise<Terms | null> {
  const { data } = await api.get<Terms | null>(`/api/deals/${dealId}/terms`)
  return data
}

export async function proposeTerms(dealId: string, input: TermsInput): Promise<Terms> {
  const { data } = await api.post<Terms>(`/api/deals/${dealId}/terms`, input)
  return data
}

/** T3.36–T3.39 — every other card goes through one endpoint. */
export async function raiseCard(
  dealId: string,
  kind: string,
  payload: Record<string, unknown> = {},
  text?: string,
): Promise<VaultMessage> {
  const { data } = await api.post<VaultMessage>(`/api/deals/${dealId}/cards`, {
    kind,
    payload,
    text,
  })
  return data
}

/** T3.11.27 — a declaration and the photographs that prove it, in one request.
 *
 *  «Без фото карточка в чат добавляться не должна» (owner, 2026-09-12). Two
 *  requests could not promise that: the card was committed first, and a refused
 *  upload then left a declaration in an append-only chain that nobody could
 *  confirm and nobody could take back. The server validates every file before
 *  it writes anything, and one transaction covers both.
 *
 *  The kind of attachment is not passed: the card's own spec declares what
 *  evidence it requires, and a client naming a different one could only be
 *  wrong.
 */
export async function raiseCardWithFiles(
  dealId: string,
  kind: string,
  files: File[],
  payload: Record<string, unknown> = {},
  text?: string,
): Promise<VaultMessage> {
  const form = new FormData()
  form.append('kind', kind)
  form.append('payload', JSON.stringify(payload))
  if (text) form.append('text', text)
  for (const file of files) form.append('files', file)
  const { data } = await api.post<VaultMessage>(
    `/api/deals/${dealId}/cards/with-files`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

/** T3.11.27 — «я сейчас правлю», for the next two minutes.
 *
 *  Taken before the change and released by it. While it is open the other side
 *  neither edits nor confirms the agreement, so what they read next is a
 *  finished version rather than somebody's second thoughts. `409` means the
 *  other side got there first — «запускай ещё раз».
 */
export const takeEditHold = (dealId: string) =>
  api.post<{ until: string }>(`/api/deals/${dealId}/terms/hold`)
