import api from './client'

export type ParamValueType = 'percent' | 'decimal' | 'integer' | 'string'
export type ParamSource = 'default' | 'global' | 'corridor'

export interface ParamCurrent {
  key: string
  scope: string
  value: string
  value_type: ParamValueType
  group: string
  approved: boolean
  note: string
  source: ParamSource
  effective_from: string | null
  comment: string
}

export interface ParamVersion {
  id: string
  key: string
  scope: string
  value: string
  value_type: ParamValueType
  effective_from: string
  comment: string
  created_by_id: string | null
  created_at: string
}

export async function listParams(scope = 'global'): Promise<ParamCurrent[]> {
  const { data } = await api.get<ParamCurrent[]>('/api/admin/params', { params: { scope } })
  return data
}

export async function paramHistory(key: string, scope?: string): Promise<ParamVersion[]> {
  const { data } = await api.get<ParamVersion[]>(`/api/admin/params/${key}/history`, {
    params: scope ? { scope } : undefined,
  })
  return data
}

export async function setParam(input: {
  key: string
  value: string
  scope?: string
  comment?: string
  effective_from?: string
}): Promise<ParamVersion> {
  const { data } = await api.post<ParamVersion>('/api/admin/params', input)
  return data
}
