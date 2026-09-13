import api from './client'
import type { Page } from './pagination'

/** T3.11.15 — one flight of a trip. `order` is assigned on write; the client
 *  sends the chain in the order it means. */
export interface TripLeg {
  order: number
  origin: string
  destination: string
  depart_at: string
  /** T3.11.07 — when this flight lands. Asked for the **end of the route** and
   *  null everywhere else, including on every trip published before 2026-09-06:
   *  a landing time the carrier does not know is not one to invent. */
  arrive_at?: string | null
  /** T3.11.07 — the city behind each code, resolved by the API from the airport
   *  table. Null for a code we do not know; the card then prints the code alone.
   *  Never stored on the trip — the code is what the carrier stated. */
  origin_city?: string | null
  destination_city?: string | null
  /** Who is actually on the plane. 16.9 % of real posts claim "in person" and
   *  some of those same posts add "(a friend is flying)" — so it is declared,
   *  not inferred, and `proxy` is a normal answer rather than a confession. */
  flown_by: 'self' | 'proxy'
}

export type TripLegInput = Omit<
  TripLeg,
  'order' | 'origin_city' | 'destination_city'
>

/** T3.11.15 — how cargo is taken at one end of the route. Separate at each end:
 *  carriers routinely accept at an address in one country and meet in person in
 *  the other. `points` is free text — districts and satellite cities, which an
 *  airport picker cannot express. */
export interface HandoverSide {
  methods: string[]
  points: string[]
  /** T3.11.07 — ids into the carrier's own lists, not copies of their text: a
   *  person who corrects a typo in their address must not have to republish
   *  every trip that mentions it. */
  address_id?: string | null
  meeting_place_id?: string | null
  /** Third level of the chain — service → method → which service. Free strings,
   *  not codes: the catalogue has no external source and must not be able to
   *  say the one company collecting parcels in a town does not exist. */
  postal_services?: string[]
}

export type SpaceKind = 'cabin' | 'checked_partial' | 'checked_full' | 'unspecified'
export type SizeHint = 'small' | 'medium' | 'large'

/** T3.11.07 — the exclusions carriers actually write, and nothing else. Mirrors
 *  `models.marketplace.EXCLUSIONS`. Cigarettes and tobacco are one entry: they
 *  are one refusal written two ways. */
export const EXCLUSIONS = ['tobacco', 'alcohol', 'food', 'luxury'] as const
export type Exclusion = (typeof EXCLUSIONS)[number]

/** T3.11.07 — what the carrier does around the flight rather than on it.
 *  Mirrors `models.marketplace.TRIP_SERVICES`. Onward shipping inside the
 *  destination country appears in 44.9 % of real posts, marketplace pickup in
 *  19 %, buying to order in 18 %. */
export const TRIP_SERVICES = [
  'domestic_shipping',
  'marketplace_pickup',
  'purchase_on_request',
  'door_delivery',
  'photo_report',
] as const
export type TripService = (typeof TRIP_SERVICES)[number]

/** T3.11.07 — the settlement model, and answering it is obligatory (owner's
 *  decision 2026-09-08).
 *
 *  Three, because they separate *when* the money moves from *where it lives* —
 *  the pair that actually differs for the two people: cash is settled hand to
 *  hand at the door, e-money by two phones, the wallet by neither. The previous
 *  two (`on_platform` / `off_platform`) folded the first two together on the
 *  grounds that «cash or transfer?» is the same question as «which system?» —
 *  right about the words, wrong about the people.
 *
 *  Obligatory on the trip, not final in the deal: the agreement carries a
 *  `payment` section both sides confirm, so the two of them may settle
 *  differently by agreeing to. */
export const PAYMENT_MODELS = [
  'cash_on_delivery',
  'emoney_on_delivery',
  'platform_wallet',
] as const
export type PaymentModel = (typeof PAYMENT_MODELS)[number]

/** The one model that needs `payment_systems` beside it. Cash has no system to
 *  name, and the wallet is the system. */
export const EMONEY_MODEL: PaymentModel = 'emoney_on_delivery'


export interface Trip {
  id: string
  carrier_id: string
  carrier_name: string
  carrier_uba?: number | null
  carrier_uba_level?: 'newbie' | 'verified' | 'reliable' | 'trusted' | 'elite' | null
  /** T3.17 — the carrier declared their key lost: the account can be signed
   *  into but can no longer act. Shown before a deal is offered, not after. */
  carrier_key_lost?: boolean
  /** T3.11.15 — the denormalised head and tail of `legs`. Derived on write, so
   *  they never disagree with the chain. Search and the board stand on them. */
  origin: string
  destination: string
  depart_at: string
  legs: TripLeg[]
  /** T3.11.07 — null means the carrier did not state a weight, which is a real
   *  answer: kilograms appear in 2.4 % of real listings and `size_hint` in far
   *  more. Every card has to render the missing case. */
  capacity: number | null
  allowed_categories: string[]
  /** T3.35 — the carrier's published baseline. Null means "price on request",
   *  which is a legitimate listing rather than a missing field. */
  price_per_kg?: number | null
  min_deal_price?: number | null
  currency?: string
  max_declared_value?: number | null
  /** T3.11.07 — the money the allowance is counted in. Null means "the trip's
   *  currency": a customs allowance is denominated by the country the parcel
   *  lands in, which is routinely not what the carrier quotes prices in. */
  max_declared_value_currency?: string | null
  space_kind?: SpaceKind
  size_hint?: SizeHint | null
  handover_origin?: HandoverSide | null
  handover_destination?: HandoverSide | null
  /** T3.11.07 — null means the carrier said nothing about exclusions, which is
   *  what 94 % of this market does. An empty array would claim otherwise. */
  excluded?: Exclusion[] | null
  services?: TripService[] | null
  payment_model?: PaymentModel | null
  payment_systems?: string[] | null
  /** T_UX.15 — the rules copied into this trip when it was published. */
  carriage_rules?: string | null
  status: string
  created_at: string
  /** T3.11.16 — when the listing stops being one: the last leg's departure.
   *  A trip past it is not on the board, and no ceremony was needed to retire
   *  it. */
  expires_at?: string | null
  nostr_event_id?: string | null
  nostr_published_at?: string | null
}

/** T3.11.27 — how close a trip is to leaving (owner, 2026-09-12): «нужен
 *  указатель если рейс очень скоро и осталось мало времени… трое суток светло
 *  зелёным и оранжевым за сутки», and «рейсы должны уходить в архив, если прошла
 *  дата вылета».
 *
 *  One function for both, because they are the same question asked at four
 *  distances, and two of them already existed in two places with two answers:
 *  the board hides a flown trip server-side (`expires_at`), while the carrier's
 *  own panel kept showing it as live.
 *
 *  `flown` is decided by `expires_at` — the **last** leg's departure, the same
 *  column the board filters on, so a two-leg trip is not archived while its
 *  second flight is still ahead. The countdown is decided by `depart_at`, the
 *  first departure: that is the deadline a sender is actually racing.
 *
 *  A trip with no dates at all is `later`, never `flown`. Hiding rows we cannot
 *  date would be guessing, and the server made the same choice for the same
 *  reason.
 */
export type DepartureState = 'flown' | 'imminent' | 'soon' | 'later'

const HOUR = 60 * 60 * 1000

export function departureState(
  trip: Pick<Trip, 'depart_at' | 'expires_at'>,
  now: number = Date.now(),
): DepartureState {
  const last = trip.expires_at ?? trip.depart_at
  if (last && new Date(last).getTime() < now) return 'flown'
  if (!trip.depart_at) return 'later'
  const left = new Date(trip.depart_at).getTime() - now
  if (left < 24 * HOUR) return 'imminent'
  if (left < 72 * HOUR) return 'soon'
  return 'later'
}

/** Whole days left before the first departure. Rounded to the nearest, not up:
 *  25 hours is «день», and calling it two days tells somebody they have a day
 *  more than they have — on the one chip whose whole job is the opposite. Never
 *  below one, because zero days is what `imminent` says in words. Only
 *  meaningful for `soon`. */
export function daysToDeparture(
  trip: Pick<Trip, 'depart_at'>,
  now: number = Date.now(),
): number {
  return Math.max(
    1,
    Math.round((new Date(trip.depart_at).getTime() - now) / (24 * HOUR)),
  )
}

export interface CreateTripPayload {
  /** T3.11.15 — the route goes on the wire as a chain and only as a chain. A
   *  single-leg array is the ordinary case; the flat origin/destination/date
   *  trio no longer exists as an input. */
  legs: TripLegInput[]
  /** Omitted publishes the trip without a stated weight — the express path. */
  capacity?: number | null
  allowed_categories: string[]
  price_per_kg?: number | null
  min_deal_price?: number | null
  currency?: string
  max_declared_value?: number | null
  max_declared_value_currency?: string | null
  space_kind?: SpaceKind
  size_hint?: SizeHint | null
  handover_origin?: HandoverSide | null
  handover_destination?: HandoverSide | null
  excluded?: Exclusion[] | null
  services?: TripService[] | null
  payment_model?: PaymentModel | null
  payment_systems?: string[] | null
  /** Sent explicitly: an emptied field means "this trip has no rules", not
   *  "fall back to my profile template". */
  carriage_rules?: string | null
}

export interface TripFilters {
  origin?: string
  destination?: string
  date?: string
  /** T_UX.18 — everything one carrier is flying, for their public page. */
  carrier_id?: string
  /** T_UX.19 — `all` or a specific status. Accepted only about your own trips:
   *  a withdrawn trip is no longer a public listing. */
  status?: string
  after?: string
  limit?: number
}

export const createTrip = (payload: CreateTripPayload) =>
  api.post<Trip>('/api/trips', payload)

/** T3.11.07 — edit a published trip (owner's request 2026-09-06).
 *
 *  The same trip, not a new one: cancel-and-republish would change the id, and
 *  the id is what every inquiry, deal and Nostr event points at. The whole body
 *  goes every time — the wizard produces all of it anyway, and a partial shape
 *  would be a second thing to validate with no caller. */
export const updateTrip = (tripId: string, payload: CreateTripPayload) =>
  api.patch<Trip>(`/api/trips/${tripId}`, payload)

/** T3.11.23 — how many people asked about each of my trips, keyed by trip id.
 *
 *  The panel used to count threads, which was free while a thread was per
 *  (trip, sender). A chat is per person now, so the question is answered where
 *  the trip actually lives — on the message that raised it — and distinct chats
 *  are counted rather than messages: somebody who writes four times about one
 *  trip has asked once. */
export const tripAskCounts = () =>
  api.get<Record<string, number>>('/api/trips/ask-counts')

export const listTrips = (filters?: TripFilters) =>
  api.get<Page<Trip>>('/api/trips', { params: filters })

/** T_UX.19 — withdraw a published trip. Cancelled, not deleted: somebody may
 *  already be talking about it. */
export const cancelTrip = (tripId: string) =>
  api.post<Trip>(`/api/trips/${tripId}/cancel`)
