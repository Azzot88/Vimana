import api from './client'
import type { Page } from './pagination'
import type { User } from './auth'
import type { VaultMessage } from './dealvault'

export type DisputeStatus = 'open' | 'claimed' | 'resolved'

export interface Dispute {
  id: string
  deal_id: string
  opened_by: string
  arbiter_id: string | null
  reason: string
  status: DisputeStatus
  verdict: string | null
  created_at: string
  resolved_at: string | null
}

export const openDispute = (dealId: string, reason: string) =>
  api.post<Dispute>(`/api/deals/${dealId}/dispute`, { reason })

export const listDisputes = (params?: { after?: string; limit?: number }) =>
  api.get<Page<Dispute>>('/api/admin/disputes', { params })

export const claimDispute = (disputeId: string) =>
  api.post<Dispute>(`/api/disputes/${disputeId}/claim`)

export const resolveDispute = (
  disputeId: string,
  verdict: string,
  closes_deal = false,
) => api.post<Dispute>(`/api/disputes/${disputeId}/resolve`, { verdict, closes_deal })

export const readVaultAsArbiter = (
  dealId: string,
  params?: { after?: string; limit?: number },
) =>
  api.get<Page<VaultMessage>>(`/api/admin/deals/${dealId}/vault`, { params })

export const listAllUsers = (params?: {
  after?: string
  limit?: number
  email_contains?: string
}) => api.get<Page<User>>('/api/admin/users', { params })

export const promoteArbiter = (userId: string, isArbiter: boolean) =>
  api.post<User>(`/api/admin/users/${userId}/promote-arbiter`, {
    is_arbiter: isArbiter,
  })

/** T_TEST.3 — superuser hard-delete for e2e/junk cleanup. Cascade. */
export const deleteUser = (userId: string) =>
  api.delete<void>(`/api/admin/users/${userId}`)

/** T3.8 — how many stored files nobody has looked at yet.
 *
 *  `pending` is not "safe": it means no scanner has seen the bytes, either
 *  because none is configured or because it was unreachable when the file
 *  arrived. `scanner_configured` separates a queue that is draining from one
 *  that never will. */
export interface ScanQueue {
  pending: number
  infected: number
  clean: number
  scanner_configured: boolean
}

export const getScanQueue = () => api.get<ScanQueue>('/api/admin/scan-queue')
