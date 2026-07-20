import api from './client'

export interface Address {
  id: string
  label: string
  country_iso: string
  city: string | null
  city_geoname_id: number | null
  street: string | null
  postal_code: string | null
  note: string | null
  is_default: boolean
  created_at: string
}

export interface AddressInput {
  label: string
  country_iso: string
  city?: string | null
  city_geoname_id?: number | null
  street?: string | null
  postal_code?: string | null
  note?: string | null
  is_default?: boolean
}

export const listAddresses = () => api.get<Address[]>('/api/me/addresses')

export const createAddress = (data: AddressInput) =>
  api.post<Address>('/api/me/addresses', data)

export const updateAddress = (id: string, patch: Partial<AddressInput>) =>
  api.patch<Address>(`/api/me/addresses/${id}`, patch)

export const makeAddressDefault = (id: string) =>
  api.post<Address>(`/api/me/addresses/${id}/default`)

export const deleteAddress = (id: string) =>
  api.delete<void>(`/api/me/addresses/${id}`)
