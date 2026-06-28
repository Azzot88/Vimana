import api from './client'

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
  trip_id: string
  sender_id: string
  sender_name: string
  carrier_id: string
  carrier_name: string
  origin: string
  destination: string
  depart_at: string
  cargo_description: string
  cargo_weight: number
  cargo_category: string
  status: DealStatus
  created_at: string
}

export interface MatchDealPayload {
  trip_id: string
  cargo_description: string
  cargo_weight: number
  cargo_category: string
}

export interface DealEvent {
  id: string
  deal_id: string
  kind: string
  actor_id: string
  note: string | null
  created_at: string
}

export const matchDeal = (payload: MatchDealPayload) =>
  api.post<Deal>('/api/deals/match', payload)

export const acceptDeal = (dealId: string) =>
  api.post<Deal>(`/api/deals/${dealId}/accept`)

export const addEvent = (dealId: string, kind: string, note?: string) =>
  api.post<DealEvent>(`/api/deals/${dealId}/events`, { kind, note })

export const confirmDeal = (dealId: string) =>
  api.post<Deal>(`/api/deals/${dealId}/confirm`)

export const listDeals = () =>
  api.get<Deal[]>('/api/deals')

export const getDeal = (dealId: string) =>
  api.get<Deal>(`/api/deals/${dealId}`)
