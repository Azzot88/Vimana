import api from './client'
import type { Page } from './pagination'

export interface Trip {
  id: string
  carrier_id: string
  carrier_name: string
  carrier_uba?: number | null
  carrier_uba_level?: 'newbie' | 'verified' | 'reliable' | 'trusted' | 'elite' | null
  /** T3.17 — the carrier declared their key lost: the account can be signed
   *  into but can no longer act. Shown before a deal is offered, not after. */
  carrier_key_lost?: boolean
  origin: string
  destination: string
  depart_at: string
  capacity: number
  allowed_categories: string[]
  /** T3.35 — the carrier's published baseline. Null means "price on request",
   *  which is a legitimate listing rather than a missing field. */
  price_per_kg?: number | null
  min_deal_price?: number | null
  currency?: string
  allowed_handover_methods?: string[] | null
  max_declared_value?: number | null
  status: string
  created_at: string
  nostr_event_id?: string | null
  nostr_published_at?: string | null
}

export interface CreateTripPayload {
  origin: string
  destination: string
  depart_at: string
  capacity: number
  allowed_categories: string[]
  price_per_kg?: number | null
  min_deal_price?: number | null
  currency?: string
  allowed_handover_methods?: string[] | null
  max_declared_value?: number | null
}

export interface TripFilters {
  origin?: string
  destination?: string
  date?: string
  after?: string
  limit?: number
}

export const createTrip = (payload: CreateTripPayload) =>
  api.post<Trip>('/api/trips', payload)

export const listTrips = (filters?: TripFilters) =>
  api.get<Page<Trip>>('/api/trips', { params: filters })
