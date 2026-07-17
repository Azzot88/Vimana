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
