import api from './client'

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
  payment_method?: 'cash' | 'platform' | 'escrow'
  description?: string | null
  supersedes_id?: string | null
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
) {
  const { data } = await api.post(`/api/deals/${dealId}/cards`, { kind, payload, text })
  return data
}
