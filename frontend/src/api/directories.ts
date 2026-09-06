import api from './client'

/** T3.11.07 — one row of either catalogue: postal services or payment systems.
 *  Same shape on purpose; they answer different questions with the same kind of
 *  answer, and the picker that renders them is the same picker. */
export interface DirectoryEntry {
  code: string
  name: string
}

/** Who can carry a parcel onward **inside the destination country**, after the
 *  flight has landed. Local services only: a carrier posting a parcel inside one
 *  country ships with what is near them, and a list topped by three
 *  international couriers describes a business rather than a person with one
 *  pick-up point down the road.
 *
 *  An empty answer is normal — ~55 countries are covered — and the form falls
 *  back to typing the name by hand. */
export const listPostalServices = (country: string) =>
  api.get<DirectoryEntry[]>('/api/postal-services', { params: { country } })

/** How money can move when it moves outside the platform. Arrival country
 *  first, then departure: settlement most often happens where the cargo changes
 *  hands, but a carrier living at the departure end still needs their own
 *  systems offered rather than typed out. */
export const listPaymentSystems = (arrival?: string, departure?: string) =>
  api.get<DirectoryEntry[]>('/api/payment-systems', {
    params: { arrival, departure },
  })
