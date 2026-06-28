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
  order_id: string
  trip_id: string
  sender_id: string
  carrier_id: string
  recipient_id: string | null
  status: DealStatus
  created_at: string
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

export const acceptDeal = (dealId: string) =>
  api.post<Deal>(`/api/deals/${dealId}/accept`)

export const addEvent = (dealId: string, event_type: string, note?: string) =>
  api.post<DealEvent>(`/api/deals/${dealId}/event`, {
    event_type,
    payload: note ? { note } : null,
  })

export const confirmDeal = (dealId: string) =>
  api.post<Deal>(`/api/deals/${dealId}/confirm`)

export const listDeals = () =>
  api.get<Deal[]>('/api/deals')

export const getDeal = (dealId: string) =>
  api.get<DealDetail>(`/api/deals/${dealId}`)
