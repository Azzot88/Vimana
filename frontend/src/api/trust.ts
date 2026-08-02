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
  /** T_TRUST.1 — the newest live vouch. Three from four years ago is a
   *  different statement from three from last month. */
  last_vouched_at: string | null
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
  /** T_TRUST.1 — the dates the claims above rest on. A level or a counter with
   *  no date is a present-tense statement about something that happened once
   *  (`D-EVIDENCE-DECAYS`). */
  verified_at: string | null
  last_vouched_at: string | null
  verifications_issued_count: number | null
  verifications_received_count: number | null
  dealt_with_count: number | null
  key_lost: boolean
  /** T3.23 — when the key changed, and what it was. Anything signed before
   *  that date belongs to a key this identity no longer holds. */
  identity_changed_at: string | null
  previous_npub: string | null
  /** T3.19 — present only for a retired identity seen in full. Null on a live
   *  one is not a missing field: there is no record to close while the key
   *  still signs. */
  archive: ArchiveRecord | null
}

/**
 * T3.19 — the record of an identity that can no longer act.
 *
 * Every number here was counted, never estimated, and every total comes with
 * the set it was counted from — `deals_closed` next to `deals_total`,
 * `routes_measured` next to `routes_closed`. There is no rate, no average and
 * no score, because none of those were measured.
 *
 * `straight_line_km` says so in its own name: it is a great-circle arc, real
 * tracks run 3–7% longer, and it measures where a parcel went rather than what
 * an aircraft flew. `capacity_kg` is capacity carriers *declared* on completed
 * trips — nothing was ever weighed. Labels must not promise more than this.
 */
export interface ArchiveRecord {
  retired_at: string
  chain_entries: number
  signatures: number
  first_signature_at: string | null
  last_signature_at: string | null
  deals_total: number
  deals_closed: number
  routes_measured: number
  routes_closed: number
  straight_line_km: number | null
  longest_hop_km: number | null
  longest_hop_route: string | null
  trips_completed: number
  capacity_kg: number | null
  /** T3.20 — how far the record is checkable without taking our word. An anchor
   *  publishes a chain head to relays we do not control, so everything beneath
   *  it carries someone else's timestamp. Null means no anchor exists yet, and
   *  the card must then claim nothing of the kind. */
  last_anchor_at: string | null
  anchored_deals: number
}

/** No auth required — and none is sent when the visitor has no session. */
export const getIdentity = (npub: string) =>
  api.get<PublicIdentity>(`/api/identities/${npub}`)
