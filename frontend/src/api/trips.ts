import api from './client'
import type { Page } from './pagination'

export interface Trip {
  id: string
  carrier_id: string
  carrier_name: string
  carrier_uba?: number | null
  carrier_uba_level?: 'newbie' | 'verified' | 'reliable' | 'trusted' | 'elite' | null
  origin: string
  destination: string
  depart_at: string
  capacity: number
  allowed_categories: string[]
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
