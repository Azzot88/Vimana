import api from './client'

export interface SignedTripEvent {
  trip_id: string
  id: string
  pubkey: string
  created_at: number
  kind: number
  tags: string[][]
  content: string
  sig: string
}

export interface PublishResult {
  event_id: string
  relays: Record<string, boolean>
  forced?: boolean
}

export interface NostrMetrics {
  success_count: number
  error_count: number
  last_attempt_at: string | null
}

export const publishSignedEvent = (event: SignedTripEvent) =>
  api.post<PublishResult>('/api/nostr/publish-signed', event)

export const republishTrip = (tripId: string) =>
  api.post<PublishResult>(`/api/nostr/republish/${tripId}`)

export const getNostrMetrics = () =>
  api.get<NostrMetrics>('/api/nostr/metrics')
