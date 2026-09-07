import api from './client'
import type { Page } from './pagination'

export interface Inquiry {
  id: string
  /** T3.11.23 — echoed back when you opened the chat from a trip; the chat
   *  itself does not belong to one, so the list leaves it out. */
  trip_id: string | null
  sender_id: string
  carrier_id: string
  deal_id: string | null
  /** T3.11.23 — the person the chat is with, by name, and how many deals are
   *  nested in it. The list of chats is a list of people; the count decides
   *  whether a choice of deal is offered at all. */
  counterparty_name?: string | null
  deal_count?: number
  created_at: string
}

export interface InquiryMessage {
  id: string
  inquiry_id: string
  sender_id: string
  text: string | null
  created_at: string
}

export const openInquiry = (tripId: string) =>
  api.post<Inquiry>(`/api/trips/${tripId}/inquiry`)

export const listMyInquiries = () => api.get<Inquiry[]>('/api/inquiries')

export const listInquiryMessages = (
  inquiryId: string,
  params?: { after?: string; limit?: number },
) =>
  api.get<Page<InquiryMessage>>(`/api/inquiries/${inquiryId}/messages`, {
    params,
  })

/** T3.11.23 — `aboutTripId` is what keeps «пишу про этот рейс» expressible now
 *  that the thread belongs to the person rather than to the trip. Optional,
 *  because most messages are not about a trip: they are the rest of the
 *  conversation. */
export const postInquiryMessage = (
  inquiryId: string,
  text: string,
  aboutTripId?: string,
) =>
  api.post<InquiryMessage>(`/api/inquiries/${inquiryId}/messages`, {
    text,
    about_trip_id: aboutTripId,
  })

export const shareAddressInInquiry = (inquiryId: string, addressId?: string) =>
  api.post<InquiryMessage>(
    `/api/inquiries/${inquiryId}/messages/share-address`,
    addressId ? { address_id: addressId } : {},
  )
