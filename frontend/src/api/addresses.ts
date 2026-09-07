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
  /** T3.11.07 — where this place is. The trip form offers meeting places for one
   *  end of a route; without a country it offered a Moscow landmark to somebody
   *  arriving in Dubai. Null on rows that predate the field — those are offered
   *  everywhere, which is what they already did. */
  country_iso: string | null
  /** Asked for meeting places and not for payment methods: «у метро Фили» is
   *  only findable if you know it is Moscow. */
  city: string | null
  is_default: boolean
  created_at: string
}

export interface MeetingPlaceInput {
  description: string
  country_iso: string
  city?: string | null
  is_default?: boolean
}

export const listMeetingPlaces = () =>
  api.get<MeetingPlace[]>('/api/me/meeting-places')

export const createMeetingPlace = (place: MeetingPlaceInput) =>
  api.post<MeetingPlace>('/api/me/meeting-places', place)

export const updateMeetingPlace = (
  id: string,
  place: Partial<MeetingPlaceInput>,
) => api.patch<MeetingPlace>(`/api/me/meeting-places/${id}`, place)

export const makeMeetingPlaceDefault = (id: string) =>
  api.post<MeetingPlace>(`/api/me/meeting-places/${id}/default`)

export const deleteMeetingPlace = (id: string) =>
  api.delete(`/api/me/meeting-places/${id}`)
