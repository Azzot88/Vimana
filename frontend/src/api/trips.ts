import api from './client'
import type { Page } from './pagination'

/** T3.11.15 — one flight of a trip. `order` is assigned on write; the client
 *  sends the chain in the order it means. */
export interface TripLeg {
  order: number
  origin: string
  destination: string
  depart_at: string
  /** Who is actually on the plane. 16.9 % of real posts claim "in person" and
   *  some of those same posts add "(a friend is flying)" — so it is declared,
   *  not inferred, and `proxy` is a normal answer rather than a confession. */
  flown_by: 'self' | 'proxy'
}

export type TripLegInput = Omit<TripLeg, 'order'>

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

/** T3.11.07 — the settlement model. Stated by 61.7 % of this market; a concrete
 *  price by 0.1 %. Null is "did not say", not "on delivery". */
/** Two, not three. Cash is not a peer of "transfer" — it is one of the systems
 *  people settle in outside the platform, so it lives in `payment_systems` and
 *  the model says only whether the money touches the platform. */
export const PAYMENT_MODELS = ['on_platform', 'off_platform'] as const
export type PaymentModel = (typeof PAYMENT_MODELS)[number]

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
  nostr_event_id?: string | null
  nostr_published_at?: string | null
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

export const listTrips = (filters?: TripFilters) =>
  api.get<Page<Trip>>('/api/trips', { params: filters })

/** T_UX.19 — withdraw a published trip. Cancelled, not deleted: somebody may
 *  already be talking about it. */
export const cancelTrip = (tripId: string) =>
  api.post<Trip>(`/api/trips/${tripId}/cancel`)
