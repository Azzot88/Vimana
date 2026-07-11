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

export const listAllUsers = (params?: { after?: string; limit?: number }) =>
  api.get<Page<User>>('/api/admin/users', { params })

export const promoteArbiter = (userId: string, isArbiter: boolean) =>
  api.post<User>(`/api/admin/users/${userId}/promote-arbiter`, {
    is_arbiter: isArbiter,
  })
