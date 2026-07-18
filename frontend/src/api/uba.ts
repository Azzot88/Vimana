import api from './client'

export type UBALevel = 'newbie' | 'verified' | 'reliable' | 'trusted' | 'elite'

export interface UBAComponents {
  f_count: number
  q_count: number
  v_sum: number
  d_peak: number
  verify_level: string | null
}

export interface UBAResponse {
  user_id: string
  uba: number
  level: UBALevel
  components: UBAComponents
}

export const getMyUba = () => api.get<UBAResponse>('/api/me/uba')

export const getUserUba = (userId: string) =>
  api.get<UBAResponse>(`/api/users/${userId}/uba`)
