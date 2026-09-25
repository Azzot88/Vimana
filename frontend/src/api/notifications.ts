import api from './client'

/** T_UX.29 pt.7 — the bell's data.
 *
 *  Functions (PROJECT §6.2a):
 *  - `listNotifications`, `unreadCount`, `markRead`, `subscribePush` — called by
 *    `components/NotificationBell` and `pages/DealVaultPage`.
 */
export type NotificationKind =
  | 'chat.message'
  | 'trip.response'
  | 'request.new'
  | 'deal.status'
  // T_UX.31
  | 'trip.corridor'
  | 'recipient.offer'
  | 'dispute.offer'

export interface AppNotification {
  id: string
  kind: NotificationKind | string
  deal_id: string | null
  trip_id: string | null
  payload: Record<string, unknown> | null
  created_at: string
  read_at: string | null
}

export const listNotifications = (limit = 30) =>
  api.get<AppNotification[]>('/api/notifications', { params: { limit } })

export const unreadCount = () =>
  api.get<{ unread: number }>('/api/notifications/unread-count')

/** Mark as **seen**, which is not the same as «clicked»: the deal screen calls
 *  this for its own deal while it is open, which is how «изменения в активном
 *  окне не показывать» is implemented (owner, 2026-09-20). */
export const markRead = (body: { ids?: string[]; deal_id?: string }) =>
  api.post<{ unread: number }>('/api/notifications/read', body)

/** The push seam. Nothing sends to these yet — see `models/notification.py`. */
export const subscribePush = (body: {
  endpoint: string
  p256dh: string
  auth: string
}) => api.post('/api/notifications/push', body)
