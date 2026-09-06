import api from './client'

export interface Category {
  name_key: string
  is_default: boolean
  usage_count: number
  /** T3.11.07 — the server's cold-start order, seeded from how often this
   *  market names each thing. `usage_count` outranks it once there is any, so
   *  the list arrives already ordered and the picker does not re-sort. */
  sort_order: number
}

export const listCategories = (q = '') =>
  api.get<Category[]>('/api/categories', { params: { q } })
