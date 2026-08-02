import api from './client'

export type TrustEdgeKind = 'peer_verified' | 'dealt_with' | 'invited'

export interface TrustCircles {
  depth: number
  kind: TrustEdgeKind | null
  circles: Record<string, string[]>
  total_reachable: number
}

export interface TrustMetrics {
  subject_id: string
  verifications_issued_count: number
  verifications_received_count: number
  dealt_with_count: number
  distance_from_viewer: number | null
}

export const getMyTrustCircle = (params?: { depth?: number; kind?: TrustEdgeKind }) =>
  api.get<TrustCircles>('/api/me/trust-circle', { params })

export const getUserTrustMetrics = (userId: string) =>
  api.get<TrustMetrics>(`/api/users/${userId}/trust-metrics`)

// ── T3.18 — the public identity page ─────────────────────────────────────────

export interface PublicIdentity {
  npub: string
  /** What this response actually contains: `full`, `minimal`. A `hidden`
   *  identity answers 404 — 403 would confirm it exists. */
  visibility: 'full' | 'minimal'
  display_name: string | null
  avatar_url: string | null
  member_since: string | null
  uba: number | null
  uba_level: string | null
  highest_verification_level: string | null
  verifications_issued_count: number | null
  verifications_received_count: number | null
  dealt_with_count: number | null
  key_lost: boolean
  /** T3.23 — when the key changed, and what it was. Anything signed before
   *  that date belongs to a key this identity no longer holds. */
  identity_changed_at: string | null
  previous_npub: string | null
}

/** No auth required — and none is sent when the visitor has no session. */
export const getIdentity = (npub: string) =>
  api.get<PublicIdentity>(`/api/identities/${npub}`)
