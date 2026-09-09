import api from './client'

/** T3.11.19 — the sender's side of the market.
 *
 *  366 posts in the dump are «кто летит в ближайшие дни ЛА — Москва?». At a
 *  five-day median horizon that is the rational move rather than a failure to
 *  use the board: at the moment the sender looks, the trip they need does not
 *  exist yet.
 */
export interface SenderRequest {
  id: string
  origin: string
  destination: string
  window_from: string
  window_to: string
  what: string | null
  /** Off means «I am asking, do not write to me» — a real answer, and the
   *  difference between a request and a subscription. */
  notify: boolean
  /** Closed by the sender or by the window running out. Closed, never deleted:
   *  what people asked for and did not get is the most useful thing this table
   *  knows. */
  is_open: boolean
  created_at: string
}

export interface RequestInput {
  origin: string
  destination: string
  window_from: string
  window_to: string
  what?: string | null
  notify?: boolean
}

/** What people are waiting for, counted. **No names**: who asked is the
 *  senders' business, and a list would turn requests into leads to work
 *  through. */
export interface CorridorDemand {
  origin: string
  destination: string
  waiting: number
}

export const fileRequest = (body: RequestInput) =>
  api.post<SenderRequest>('/api/requests', body)

export const myRequests = () => api.get<SenderRequest[]>('/api/requests')

export const corridorDemand = (limit = 20) =>
  api.get<CorridorDemand[]>('/api/requests/open', { params: { limit } })

export const updateRequest = (
  id: string,
  patch: { is_open?: boolean; notify?: boolean },
) => api.patch<SenderRequest>(`/api/requests/${id}`, patch)
