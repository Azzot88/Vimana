import api from './client'

export interface Category {
  name_key: string
  is_default: boolean
  usage_count: number
}

export const listCategories = (q = '') =>
  api.get<Category[]>('/api/categories', { params: { q } })
