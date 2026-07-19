import api from './client'

export type RouteStatus = 'standard' | 'attention' | 'complex' | 'restricted'
export type NoticeSeverity = 'info' | 'warning' | 'alert'
export type NoticeSurface = 'footer' | 'trip_card' | 'deal_page' | 'all'

export interface RouteNote {
  id: string
  origin_iso: string
  destination_iso: string
  status: RouteStatus
  severity: NoticeSeverity
  headline: string
  body: string
  active_from: string
  active_until: string | null
}

export interface PlatformNotice {
  id: string
  key: string
  severity: NoticeSeverity
  target_surface: NoticeSurface
  headline: string
  body: string
  active_from: string
  active_until: string | null
}

export const listRouteNotes = (params?: { origin?: string; destination?: string }) =>
  api.get<RouteNote[]>('/api/route-notes', { params })

export const listPlatformNotices = (params?: { surface?: NoticeSurface }) =>
  api.get<PlatformNotice[]>('/api/platform-notices', { params })

export const createRouteNote = (data: Partial<RouteNote>) =>
  api.post<RouteNote>('/api/admin/route-notes', data)

export const deleteRouteNote = (id: string) =>
  api.delete<void>(`/api/admin/route-notes/${id}`)

export const createPlatformNotice = (data: Partial<PlatformNotice>) =>
  api.post<PlatformNotice>('/api/admin/platform-notices', data)

export const deletePlatformNotice = (id: string) =>
  api.delete<void>(`/api/admin/platform-notices/${id}`)
