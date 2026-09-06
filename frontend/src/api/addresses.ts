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

/** T3.11.07 — where this person is willing to meet, in their own words.
 *
 *  Not an address: an address is where a parcel is sent and carries the
 *  structure the post office needs, a meeting place is «у метро Фили, у выхода
 *  №3». Same list mechanics — several, one default, deleting the default
 *  promotes another — which is why both live in one module here and in one
 *  router on the server.
 */
export interface MeetingPlace {
  id: string
  description: string
  is_default: boolean
  created_at: string
}

export const listMeetingPlaces = () =>
  api.get<MeetingPlace[]>('/api/me/meeting-places')

export const createMeetingPlace = (description: string, isDefault = false) =>
  api.post<MeetingPlace>('/api/me/meeting-places', {
    description,
    is_default: isDefault,
  })

export const updateMeetingPlace = (id: string, description: string) =>
  api.patch<MeetingPlace>(`/api/me/meeting-places/${id}`, { description })

export const makeMeetingPlaceDefault = (id: string) =>
  api.post<MeetingPlace>(`/api/me/meeting-places/${id}/default`)

export const deleteMeetingPlace = (id: string) =>
  api.delete(`/api/me/meeting-places/${id}`)
