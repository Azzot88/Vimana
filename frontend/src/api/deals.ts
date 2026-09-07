import api from './client'
import type { Page } from './pagination'

export type DealStatus =
  | 'draft'
  | 'matched'
  | 'accepted'
  | 'in_transit'
  | 'delivered'
  | 'confirmed'
  | 'closed'
  | 'disputed'

export interface Deal {
  id: string
  order_id: string
  trip_id: string
  sender_id: string
  carrier_id: string
  recipient_id: string | null
  status: DealStatus
  created_at: string
  // T3.11.26 — `origin`/`destination` now come with the list too, from a
  // batched lookup over the page's trips. `cargo_description` still does not:
  // it lives on the order and only the detail endpoint joins it.
  origin?: string
  destination?: string
  cargo_description?: string
  /** T3.11.26 — who the deal is with and where it goes. Filled by the list
   *  endpoint from batched lookups: the deals page groups by person, and a
   *  column of truncated UUIDs is a list nobody can choose from. */
  sender_name?: string | null
  carrier_name?: string | null
  /** T3.11.23 — the deal card: the number people say out loud, the chat the
   *  deal is nested in, and the two halves of a name nobody has to type. */
  shipment_no?: string | null
  chat_id?: string | null
  cargo_category?: string | null
  price_total?: number | null
  currency?: string | null
}

export interface DealDetail extends Deal {
  origin: string
  destination: string
  depart_at: string
  sender_name: string
  carrier_name: string
  cargo_description: string
  cargo_category: string
  declared_value: number
  currency: string
  /** T_UX.15 — the rules copied into this trip when it was published, not the
   *  carrier's current template. */
  carriage_rules?: string | null
}

export interface MatchDealPayload {
  trip_id: string
  order: {
    recipient_contact: string
    origin: string
    destination: string
    category: string
    declared_value: number
    currency?: string
    description?: string
  }
}

export interface DealEvent {
  id: string
  deal_id: string
  event_type: string
  payload: Record<string, unknown> | null
  actor_id: string
  timestamp: string
}

export const matchDeal = (payload: MatchDealPayload) =>
  api.post<Deal>('/api/deals/match', payload)

export const addEvent = (dealId: string, event_type: string, note?: string) =>
  api.post<DealEvent>(`/api/deals/${dealId}/event`, {
    event_type,
    payload: note ? { note } : null,
  })

export const confirmDeal = (dealId: string) =>
  api.post<Deal>(`/api/deals/${dealId}/confirm`)

export interface DealListParams {
  /** T3.11.23 — only the deals nested in this chat, closed ones included. */
  chat_id?: string
  after?: string
  limit?: number
}

export const listDeals = (params?: DealListParams) =>
  api.get<Page<Deal>>('/api/deals', { params })

export const getDeal = (dealId: string) =>
  api.get<DealDetail>(`/api/deals/${dealId}`)
