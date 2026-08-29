import api from './client'
import type { Page } from './pagination'
import type { User } from './auth'
import type { VaultMessage } from './dealvault'
import type { RoleGrant } from './roles'

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
  /** T3.42 — only accounts holding this role. A filter, not a sort. */
  role?: string
}) => api.get<Page<User>>('/api/admin/users', { params })

/** T3.42 — propose a role. Grants nothing: the account keeps exactly the
 *  rights it had until the person accepts, so the caller must not paint the
 *  new role onto the row. */
export const offerRole = (userId: string, role: string, reason = '') =>
  api.post<RoleGrant>(`/api/admin/users/${userId}/roles`, { role, reason })

/** Take back a live role, or an offer nobody answered. Both are journalled.
 *
 *  `reason` is required by the API: it lands in the journal and in the letter
 *  the person receives. */
export const revokeRole = (userId: string, role: string, reason: string) =>
  api.delete<RoleGrant>(`/api/admin/users/${userId}/roles/${role}`, {
    data: { reason },
  })

/** Every event for one account, newest first — where the role in force came from. */
export const roleJournal = (userId: string) =>
  api.get<RoleGrant[]>(`/api/admin/users/${userId}/roles`)

/** T3.42 — offers nobody has answered yet, across all accounts.
 *
 *  Without this the only trace of an unanswered offer was the letter, sitting
 *  in the recipient's mailbox where the person who sent it cannot look. */
export interface PendingOffer extends RoleGrant {
  subject_id: string
  subject_name: string
  subject_contact: string | null
}

export const openRoleOffers = () =>
  api.get<PendingOffer[]>('/api/admin/role-offers')

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

// ── T_UX.9 pt.2 · mail console ───────────────────────────────────────────────

export interface MailCircuit {
  configured: boolean
  host: string
  port: number
  user: string
  tls: string
}

export interface MailStatus {
  live: MailCircuit
  preview: MailCircuit
  from_name: string
  locales: string[]
  kinds: string[]
  default_locale: string
}

export interface EmailTemplate {
  kind: string
  subject: string
  html: string
  text: string
}

export interface EmailTemplates {
  locale: string
  letters: EmailTemplate[]
}

export const getMailStatus = () => api.get<MailStatus>('/api/admin/email/status')

/** Renders only — no SMTP is contacted, so the page works with mail broken. */
export const getEmailTemplates = (locale: string) =>
  api.get<EmailTemplates>('/api/admin/email/templates', { params: { locale } })

/** Always the preview circuit. There is no parameter that could reach a real inbox. */
export const sendTestEmail = (to: string, kind: string, locale: string) =>
  api.post<{ delivered: boolean; to: string; subject: string }>(
    '/api/admin/email/test',
    { to, kind, locale },
  )
