        // T3.11.07 — obligatory since 2026-09-08. `null` cannot leave this form
        // any more; the publish guard below refuses before it gets here.
        payment_model: draft.paymentModel || null,
        // Only meaningful beside e-money: cash has no system to name, and the
        // server refuses a system sent with anything else.import { useId, useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import {
  createTrip,
  updateTrip,
  listTrips,
  EMONEY_MODEL,
  EXCLUSIONS,
  PAYMENT_MODELS,
  TRIP_SERVICES,
  type CreateTripPayload,
  type Exclusion,
  type PaymentModel,
  type Trip,
  type TripService,
} from '../api/trips'
import { listRouteNotes, type RouteNote } from '../api/notices'
import {
  listAddresses,
  listMeetingPlaces,
  type Address,
  type MeetingPlace,
} from '../api/addresses'
import { CURRENCIES } from '../api/auth'
// T3.11.22 — the vocabulary lives in one file now (`lib/cardForms`), the same
// one the deal card reads. A carrier cannot advertise a method no card can name
// because there is no second list left to drift.
import { HANDOVER_METHODS } from '../lib/cardForms'
import {
  listPaymentSystems,
  listPostalServices,
  type DirectoryEntry,
} from '../api/directories'
import AirportSelect from '../components/AirportSelect'
import DateTimeField from '../components/DateTimeField'
import CategoryBubbles from '../components/CategoryBubbles'
import MonoText from '../components/MonoText'
import WizardSheet from '../components/WizardSheet'
import { routeNode } from '../lib/format'
import { usePrefs } from '../hooks/usePrefs'

/** T3.11.20 — four steps, and only the first is required.
 *
 *  The order is the order of certainty. Step 1 is what the carrier knows by
 *  heart and can answer in fifteen seconds; step 4 is commercial decisions that
 *  need thinking about. Putting money earlier is the classic way to lose the
 *  people who would have published.
 */
const TOTAL_STEPS = 4

// T3.11.07 — bumped from v1 when the route became a chain, again when "who is
// flying" moved from the leg to the trip, and again when the route became a
// list of stops rather than a list of flights. Every time for the same reason:
// a draft read under the wrong shape looks filled and is not. A v3 draft holds
// `legs`, which nothing reads any more — it would open as an empty route with
// every other answer still in place, which is the worst of the two states.
const DRAFT_KEY = 'trips:draft:v4'

/** T3.11.07 — one **stop** on the route (owner's decision 2026-09-06).
 *
 *  The form used to ask for flights: a row of from / to / date, and a second
 *  row for the next flight. That is the database's shape, not the carrier's.
 *  Somebody flying Moscow → Istanbul → New York does not think "two flights",
 *  they think "one trip with a transfer in Istanbul" — and the old form made
 *  them type Istanbul twice, once as an arrival and once as a departure, with
 *  nothing stopping the two from disagreeing.
 *
 *  So the carrier now names stops, and the flights fall out of them: adding a
 *  transfer inserts one stop and produces two hops. A city cannot disagree with
 *  itself, because it is written once.
 *
 *  `departAt` is when this stop is **left**. The last stop has none — nobody
 *  departs their destination — and `nodesToLegs` never reads it.
 *
 *  Note what is *not* here: who is flying. The model keeps `flown_by` per leg,
 *  because a chain can genuinely be flown by two people, but the form asks it
 *  once for the whole trip (owner's decision 2026-09-06) — the answer is almost
 *  always the same for every leg, and asking it three times makes a real
 *  question look like a formality. */
interface NodeDraft {
  code: string
  // T3.11.07 — the country behind the code, captured when the airport is
  // picked. Postal services are offered by the country the trip lands in and
  // payment systems by its two ends; deriving that from an IATA code later
  // would be a second lookup for something the picker already had. Empty for a
  // hand-typed code, and that is a real state: the pickers then fall back to
  // typing the answer.
  country: string
  /** T3.11.07 — the city behind the code, captured when the airport is picked
   *  so the preview reads «Dubai, DXB» exactly as the board does. Empty for a
   *  hand-typed code, and then the preview prints the code alone — the same
   *  thing the board does for the same case. */
  city: string
  departAt: string
  /** T3.11.07 — when the carrier lands here. Asked only on the **last** stop
   *  (owner's decision 2026-09-06): that is the time a sender needs — when the
   *  parcel can be collected — and a carrier who knows the landing hour of each
   *  intermediate hop is rare. Empty everywhere else, and empty is a real
   *  answer rather than a gap. */
  arriveAt: string
}

const EMPTY_NODE: NodeDraft = {
  code: '',
  country: '',
  city: '',
  departAt: '',
  arriveAt: '',
}

/** The chain the API wants, derived from the stops the carrier named.
 *
 *  One direction only. The stops are the single source of the route: deriving
 *  legs on the way out and never storing them means the two cannot drift, which
 *  is the whole reason the form changed shape.
 *
 *  Called by: `validate`, `handleSubmit`, the preview, the preflight check.
 */
function nodesToLegs(nodes: NodeDraft[]) {
  return nodes.slice(0, -1).map((from, i) => ({
    origin: from.code,
    originCity: from.city,
    destination: nodes[i + 1].code,
    destinationCity: nodes[i + 1].city,
    departAt: from.departAt,
    // The landing time belongs to the flight that ends at the next stop, so it
    // is read off *that* stop rather than off this one. Only the last stop is
    // ever asked, so every earlier leg carries an empty string.
    arriveAt: nodes[i + 1].arriveAt,
  }))
}

/** A stop the carrier has finished answering — the code, and the departure
 *  unless it is the last one. Used to decide when the next transfer may be
 *  offered: a form that hands out empty rows before the first is filled shows
 *  work instead of asking for it. */
const isNodeComplete = (node: NodeDraft, isLast: boolean) =>
  Boolean(node.code && (isLast || node.departAt))

// Matches `core.trip_legs.MAX_LEGS` on the server. Real posts top out at six
// cities; the limit exists so one listing cannot become a database. Stops are
// one more than flights — two stops are one flight.
const MAX_LEGS = 10
const MAX_NODES = MAX_LEGS + 1

/** T3.11.07 — one end of the handover. `points` is one text field rather than a
 *  repeater: carriers write "Tustin, Irvine or LAX" in one breath, and three
 *  boxes to fill would be three boxes left empty. Split on commas on submit. */
interface HandoverDraft {
  methods: string[]
  points: string
  // T3.11.07 — ids into the carrier's own lists, not copies of their text: a
  // person who corrects a typo in their address should not have to republish
  // every trip that mentions it. Empty means "not chosen".
  addressId: string
  placeId: string
  // Third level of the chain (service → method → which service), typed as one
  // comma-separated line and shown as chips. Destination side only.
  postalServices: string
}

const EMPTY_HANDOVER: HandoverDraft = {
  methods: [],
  points: '',
  addressId: '',
  placeId: '',
  postalServices: '',
}


/** T3.11.07 — how far one press of an arrow or one notch of the wheel moves
 *  the customs allowance (owner's decision 2026-09-06). Allowances are round
 *  numbers — $2 000 into the US — and the figures carriers quote move in
 *  hundreds. Typing stays free: `step` constrains the stepper, not the
 *  keyboard, so an exact 1 750 is still one field away. */
const ALLOWANCE_STEP = 200

const SPACE_KINDS = ['cabin', 'checked_partial', 'checked_full'] as const
const SIZE_HINTS = ['small', 'medium', 'large'] as const

/** T3.11.07 — the weight scale runs to 32 kg (owner's decision 2026-09-06).
 *
 *  32 is the airline ceiling for a single checked bag, and 23 is the ordinary
 *  one; the old maximum of 20 could not express either. The scale is a real
 *  ruler — a tick every kilogram, so a carrier can see where 7 sits — but only
 *  the numbers people actually say are printed. Labelling all 33 would turn a
 *  scale into a wall of digits and make the eight that matter unfindable.
 */
/** The same scale in the unit the account reads in.
 *
 *  T3.11.07 — pounds are not kilograms relabelled. 23 kg is the ordinary
 *  checked bag and 32 kg the airline ceiling for one; in pounds those are the
 *  round numbers 50 and 70, and printing "50.7" beside them would make a scale
 *  built out of the numbers people say into one built out of arithmetic.
 *
 *  Storage stays metric either way — `prefs.toKg` is what goes to the API.
 */
const CAPACITY_SCALE = {
  kg: { max: 32, labelled: [0, 5, 10, 15, 20, 23, 25, 32] },
  lb: { max: 70, labelled: [0, 10, 20, 30, 40, 50, 60, 70] },
} as const

interface Draft {
  /** The stops, in order. Always at least two — an origin and a destination —
   *  and everything between them is a transfer. */
  nodes: NodeDraft[]
  // T3.11.15 — asked once for the trip and written onto every leg. "Flying in
  // person" is the most valuable claim on this market and it appears in the
  // same posts as "(a friend is flying)", so silence is not allowed to answer
  // it — but one switch answers it, not one per flight.
  flownBy: 'self' | 'proxy'
  capacity: string
  // T3.11.15 — the physical half of the capacity: what kind of room, and how
  // big a thing fits. Kilograms are named in 2.4 % of real posts and
  // "small / not big" in 9.9 %, so the number alone asks a question most
  // carriers do not answer.
  spaceKind: 'unspecified' | (typeof SPACE_KINDS)[number]
  sizeHint: '' | (typeof SIZE_HINTS)[number]
  handoverOrigin: HandoverDraft
  handoverDestination: HandoverDraft
  // T3.11.07 — a closed list, so a sender can filter on it. Empty means the
  // carrier said nothing, and that is sent as `null` rather than `[]`.
  excluded: Exclusion[]
  // T3.11.07 — what the carrier does around the flight, and how they expect to
  // be paid. The settlement model is stated by 61.7 % of this market and a
  // price by 0.1 %, so the empty string here means "did not say" and is sent
  // as `null` — not as the commonest answer.
  services: TripService[]
  paymentModel: '' | PaymentModel
  // Typed as one comma-separated line and shown as chips: what people transfer
  // through is local and changes faster than any list we could ship.
  paymentSystems: string
  categories: string[]
  alsoOnNostr: boolean
  // T3.35 — the carrier's baseline terms. Strings because they come from
  // inputs; empty means "not stated", which is a real answer.
  pricePerKg: string
  minDealPrice: string
  currency: string
  maxDeclaredValue: string
  // T3.11.07 — the allowance counts in the arrival country's money, which is
  // routinely not what the carrier quotes prices in. Empty means "the trip's
  // currency" and travels as null.
  maxDeclaredValueCurrency: string
  carriageRules: string
}

const EMPTY: Draft = {
  nodes: [{ ...EMPTY_NODE }, { ...EMPTY_NODE }],
  flownBy: 'self',
  capacity: '',
  spaceKind: 'unspecified',
  sizeHint: '',
  handoverOrigin: { ...EMPTY_HANDOVER },
  handoverDestination: { ...EMPTY_HANDOVER },
  excluded: [],
  services: [],
  paymentModel: '',
  paymentSystems: '',
  categories: [],
  alsoOnNostr: true,
  pricePerKg: '',
  minDealPrice: '',
  // T3.11.07 — empty means "use the account's default currency", the same
  // convention every other field in this draft uses. Hard-coding USD here made
  // "untouched" indistinguishable from "chose USD".
  currency: '',
  // T3.11.07 — 2 000 by default (owner's decision 2026-09-06). It is the US
  // allowance and the number this market quotes most; a blank field made every
  // carrier look up a figure they mostly already know.
  maxDeclaredValue: '2000',
  maxDeclaredValueCurrency: '',
  carriageRules: '',
}

function loadDraft(): Draft {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return EMPTY
    const parsed = JSON.parse(raw) as Partial<Draft>
    return {
      ...EMPTY,
      ...parsed,
      categories: parsed.categories ?? [],
      // A saved draft with fewer than two stops would render a route cell that
      // cannot express a flight and gives no way to add one.
      nodes:
        parsed.nodes && parsed.nodes.length >= 2
          ? parsed.nodes
          : [{ ...EMPTY_NODE }, { ...EMPTY_NODE }],
      excluded: parsed.excluded ?? [],
      services: parsed.services ?? [],
      handoverOrigin: { ...EMPTY_HANDOVER, ...parsed.handoverOrigin },
      handoverDestination: { ...EMPTY_HANDOVER, ...parsed.handoverDestination },
    }
  } catch {
    return EMPTY
  }
}

/** T3.11.07 — a handover end for the wire, or `null` when the carrier said
 *  nothing about it. Sending `{methods: [], points: []}` would record silence as
 *  an answer, and the card that reads it later could not tell the two apart.
 *
 *  Called by: `NewTripPage.handleSubmit`.
 */
/** T3.11.07 — one comma-separated line into the chips behind it.
 *
 *  Shared by the handover points and the transfer systems: both are "type what
 *  you mean, separated by commas", and two implementations of that would drift
 *  on the first edge case.
 *
 *  Called by: `toHandover`, `NewTripPage.handleSubmit`.
 */
function splitChips(value: string, limit = 8): string[] | null {
  const parts = value
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)
    .slice(0, limit)
  return parts.length > 0 ? parts : null
}

/** T3.11.07 — one stored handover end back into the shape the form edits.
 *
 *  The ids come back as they are: "same as last time" copies the whole answer,
 *  and an address the carrier still owns is still the right address. If they
 *  have since deleted it the select simply shows nothing chosen, which is the
 *  honest result and better than silently publishing a dangling id.
 *
 *  Called by: `NewTripPage.prefillFromLast`.
 */
function fromHandover(side: Trip['handover_origin']): HandoverDraft {
  return {
    methods: side?.methods ?? [],
    points: (side?.points ?? []).join(', '),
    addressId: side?.address_id ?? '',
    placeId: side?.meeting_place_id ?? '',
    postalServices: (side?.postal_services ?? []).join(', '),
  }
}

function toHandover(side: HandoverDraft) {
  // The API caps points at six; trimming here means a carrier who typed seven
  // gets a published trip rather than a validation error about a field they
  // filled in generously.
  const points = splitChips(side.points, 6) ?? []
  const postal = splitChips(side.postalServices) ?? []
  const empty =
    side.methods.length === 0 &&
    points.length === 0 &&
    postal.length === 0 &&
    !side.addressId &&
    !side.placeId
  if (empty) return null
  return {
    methods: side.methods,
    points,
    address_id: side.addressId || null,
    meeting_place_id: side.placeId || null,
    postal_services: postal,
  }
}

/** T3.11.07 — a stored trip back into the shape the form edits.
 *
 *  One function for two callers that differ in one bit. «Как в прошлый раз»
 *  copies everything **except** the dates — they are the one thing never right
 *  twice — while an edit copies them too, because an edit that silently blanked
 *  the departure would be a trap: the carrier came to change a price and would
 *  publish a trip with no date.
 *
 *  Two things deliberately do not survive either trip. The **countries** are not
 *  in the response — a trip carries IATA codes, not ISO pairs — so the postal
 *  and payment pickers stay empty until an airport is re-picked rather than
 *  being shown a catalogue guessed from a code. The **arrival** is copied only
 *  with the dates, for the same reason as the departure.
 *
 *  `toUnit` is passed rather than imported: the weight is stored metric and
 *  shown in whatever the account reads in, and a module function has no hook.
 *
 *  Called by: `prefillFromLast`, and the edit-mode effect.
 */
function draftFromTrip(
  trip: Trip,
  toUnit: (kg: number) => number,
  keepDates: boolean,
): Partial<Draft> {
  const legs = trip.legs ?? []
  const nodes: NodeDraft[] =
    legs.length > 0
      ? [
          {
            ...EMPTY_NODE,
            code: legs[0].origin,
            // The city comes back with the trip, so the preview reads the same
            // as it did on the original. The country does not — the API sends a
            // code, not an ISO pair — which is why that one still waits for the
            // airport to be re-picked.
            city: legs[0].origin_city ?? '',
            departAt: keepDates ? toLocalInput(legs[0].depart_at) : '',
          },
          ...legs.map((leg, i) => ({
            ...EMPTY_NODE,
            code: leg.destination,
            city: leg.destination_city ?? '',
            // A stop's departure is the *next* leg's, and the last stop has
            // none — which is exactly what `nodesToLegs` reads back out.
            departAt:
              keepDates && legs[i + 1] ? toLocalInput(legs[i + 1].depart_at) : '',
            arriveAt:
              keepDates && !legs[i + 1] ? toLocalInput(leg.arrive_at) : '',
          })),
        ]
      : [
          { ...EMPTY_NODE, code: trip.origin },
          { ...EMPTY_NODE, code: trip.destination },
        ]

  return {
    nodes,
    flownBy: legs[0]?.flown_by ?? 'self',
    // Stored metric, shown in the account's unit.
    capacity:
      trip.capacity != null ? String(Math.round(toUnit(trip.capacity) * 2) / 2) : '',
    spaceKind: trip.space_kind ?? 'unspecified',
    sizeHint: trip.size_hint ?? '',
    handoverOrigin: fromHandover(trip.handover_origin),
    handoverDestination: fromHandover(trip.handover_destination),
    excluded: trip.excluded ?? [],
    services: trip.services ?? [],
    paymentModel: trip.payment_model ?? '',
    paymentSystems: (trip.payment_systems ?? []).join(', '),
    categories: trip.allowed_categories ?? [],
    pricePerKg: trip.price_per_kg != null ? String(trip.price_per_kg) : '',
    minDealPrice: trip.min_deal_price != null ? String(trip.min_deal_price) : '',
    currency: trip.currency ?? 'USD',
    maxDeclaredValue:
      trip.max_declared_value != null ? String(trip.max_declared_value) : '',
    maxDeclaredValueCurrency: trip.max_declared_value_currency ?? '',
    carriageRules: trip.carriage_rules ?? '',
  }
}

/** T3.11.07 — the same trip, flown the other way (owner's request 2026-09-06).
 *
 *  A carrier who flies Dubai → New York almost always comes back, and the
 *  return listing is the outbound one with two things changed: the route runs
 *  backwards and the dates are unknown. Everything else — what they take, how
 *  much room, the settlement, the rules — is the same person with the same
 *  suitcase, and making them answer all of it again is the reason the return
 *  half of this market gets published as a line in a chat instead of a listing.
 *
 *  **The two handover ends swap, and they have to.** On the outbound, the
 *  origin block describes Dubai (where cargo is accepted) and the destination
 *  block describes New York (where it is handed over). The return is
 *  New York → Dubai: it accepts in New York and hands over in Dubai. Swapping
 *  keeps each block with its own city — including the address and the meeting
 *  place, which are rows in the carrier's profile tied to a real place.
 *
 *  **Postal services do not survive the swap.** They are asked only about the
 *  destination — onward shipping happens after landing — so the block that was
 *  the destination carries the arrival country's services, and after the swap
 *  it is the origin. Left in, they would be published on a trip whose form
 *  never shows them, for a country the parcel no longer lands in.
 *
 *  Dates are already empty: this is built on top of `draftFromTrip(…, false)`,
 *  the same "never right twice" rule as «как в прошлый раз».
 *
 *  Called by: the reverse-trip effect in `NewTripPage`.
 */
function reversedDraft(base: Partial<Draft>): Partial<Draft> {
  const nodes = [...(base.nodes ?? [])].reverse()
  const origin = { ...(base.handoverDestination ?? EMPTY_HANDOVER), postalServices: '' }
  const destination = { ...(base.handoverOrigin ?? EMPTY_HANDOVER) }
  return { ...base, nodes, handoverOrigin: origin, handoverDestination: destination }
}

/** An ISO instant into what `DateTimeField` reads: `YYYY-MM-DDTHH:mm`, local.
 *
 *  Local rather than UTC because that is what the field means everywhere else
 *  in this form — the carrier types the clock on the wall at the airport they
 *  are leaving from. Round-tripping through UTC here would move every edited
 *  departure by the offset, silently, and only for carriers not on UTC.
 */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`
}

// Feature flags for experimental input methods (voice / ticket scan).
// Kept as hook-points per PRD T1.25 — actual implementations live in
// EXP-03 / EXP-04 (see MASTERPLAN §10).
const VOICE_ENABLED = false
const SCAN_ENABLED = false

export default function NewTripPage() {
  const prefs = usePrefs()
  // T_TEST.8 — labels that stand *next to* a field name nothing. Associated by
  // id, generated per instance rather than fixed.
  // T3.11.07 — one id per stop, not one for "from" and one for "to": the route
  // is a list of stops now, and the two names described the old shape.
  const stopId = useId()
  const departId = useId()
  const arriveId = useId()
  const capacityId = useId()
  // T_TEST.8 — the slider is a second way into the same number, so it carries
  // the same name rather than a made-up one of its own. Hiding it from screen
  // readers was the other option and it is worse: dragging is the easier input
  // for some motor impairments, and the field it duplicates stays reachable.
  const capacityLabelId = useId()
  const rulesId = useId()
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)

  const [draft, setDraft] = useState<Draft>(loadDraft)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [askingToClose, setAskingToClose] = useState(false)
  // T3.11.21 — the carrier's last published trip, offered as a starting point.
  // Fetched once and kept until used: 5.4 % of this market says outright "I fly
  // every week", and for them the whole wizard is a date change.
  const [lastTrip, setLastTrip] = useState<Trip | null>(null)
  const [prefilled, setPrefilled] = useState(false)
  // T3.11.07 — the carrier's own lists, and the two catalogues the handover
  // step offers. Fetched once on mount: none of them changes while the form is
  // open, and the postal one is refetched only when the destination country
  // does.
  const [addresses, setAddresses] = useState<Address[]>([])
  const [places, setPlaces] = useState<MeetingPlace[]>([])
  const [postal, setPostal] = useState<DirectoryEntry[]>([])
  const [systems, setSystems] = useState<DirectoryEntry[]>([])

  // T3.11.20 — the step lives in the URL, not in state.
  //
  // Browser Back and the phone's back gesture then mean "previous step", which
  // is what a person pressing them at step 3 intends. Held in state instead,
  // the same press throws the whole wizard away — and a wizard you can fall out
  // of by the most ordinary gesture on the device is exactly the trap the
  // always-visible Back button exists to prevent.
  const [params, setParams] = useSearchParams()
  const step = Math.min(
    TOTAL_STEPS,
    Math.max(1, Number(params.get('step')) || 1),
  )
  /* T3.11.07 — the trip being edited, or null for a new one (owner's request
     2026-09-06). The wizard is the same four steps either way: a second form
     for editing would be the same twenty fields written twice, and the copy
     that fell behind would be the one that silently dropped an answer. */
  const editingId = params.get('edit')
  /* T3.11.07 — the trip this one is the return of (owner's request
     2026-09-06). Unlike `edit`, nothing downstream needs it: it is a
     starting point, not a target, so it is consumed once and dropped from the
     URL. A reload then falls back to the autosaved draft, which is what the
     carrier has been typing into — reprefilling from the parent would throw
     that away. */
  const reverseId = params.get('reverse')
  /* T3.11.16 — «повторить»: the same route again, dates cleared. Its own
     parameter rather than a flag on `reverse`, so the two intentions stay
     distinguishable in the address and in whatever we measure later. */
  const repeatId = params.get('repeat')
  const reversedFrom = useRef<string | null>(null)
  const goToStep = useCallback(
    (next: number, replace = false) => {
      const query: Record<string, string> = { step: String(next) }
      // Carried across every step: dropping it mid-wizard would turn an edit
      // into a second publication at whichever step the carrier pressed Next.
      const editing = params.get('edit')
      if (editing) query.edit = editing
      setParams(query, { replace })
    },
    [params, setParams],
  )

  useEffect(() => {
    // T3.11.07 — an edit is not saved as the draft. The key holds the carrier's
    // unfinished *new* trip, and writing an edit into it would throw that away
    // for somebody who only came to fix a price. An edit is a short round trip
    // and losing it costs one reopen; losing a half-written publication does
    // not.
    if (editingId) return
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
  }, [draft, editingId])

  // T_UX.15 — the standing rules from the profile are a starting point, not a
  // lock: prefilled once when the field is untouched, editable per trip.
  useEffect(() => {
    if (user?.carriage_rules && !draft.carriageRules) {
      patch({ carriageRules: user.carriage_rules })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.carriage_rules])

  const patch = useCallback((delta: Partial<Draft>) => {
    setDraft((prev) => ({ ...prev, ...delta }))
  }, [])

  /** T3.11.21 — the last published trip, so "same as last time" has something
   *  to offer. Asked for once, and only when the form is still empty: a carrier
   *  who has already started typing is not offered a way to overwrite it.
   *
   *  `status=all` because the useful precedent is the last trip they published,
   *  which by now may have flown or been withdrawn — the board filter would
   *  hide exactly the ones a regular carrier has most of.
   */
  useEffect(() => {
    if (!user?.id || editingId) return
    listTrips({ carrier_id: user.id, status: 'all', limit: 1 })
      .then(({ data }) => setLastTrip(data.items[0] ?? null))
      .catch(() => {})
  }, [user?.id])

  // T3.11.07 — the carrier's own two lists. Neither changes while the form is
  // open, so they are fetched once; a carrier who has none sees the manual
  // fields, which is the same thing the form does for a country the catalogue
  // does not cover.
  useEffect(() => {
    listAddresses()
      .then(({ data }) => setAddresses(data))
      .catch(() => {})
    listMeetingPlaces()
      .then(({ data }) => setPlaces(data))
      .catch(() => {})
  }, [])

  /* T3.11.07 — edit mode loads the trip into the form (owner's request
     2026-09-06). The panel hands it over in router state, because the board
     already has the object and a second request for something on screen is a
     spinner for nothing. A cold reload has no state, and there is no
     single-trip endpoint, so it falls back to the carrier's own listing —
     which is the one place that returns a trip of any status. */
  useEffect(() => {
    if (!editingId) return
    const passed = (location.state as { trip?: Trip } | null)?.trip
    // Merged onto EMPTY, not onto the current draft: an unfinished new trip
    // sitting in `localStorage` must not leak its answers into somebody else's
    // published one.
    if (passed && passed.id === editingId) {
      setDraft({ ...EMPTY, ...draftFromTrip(passed, prefs.toUnit, true) })
      return
    }
    listTrips({ carrier_id: user?.id, status: 'all', limit: 100 })
      .then(({ data }) => {
        const found = data.items.find((x) => x.id === editingId)
        if (found) setDraft({ ...EMPTY, ...draftFromTrip(found, prefs.toUnit, true) })
        else setError(t('trips.editNotFound') as string)
      })
      .catch(() => setError(t('trips.editNotFound') as string))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingId])

  /* T3.11.07 — «обратный рейс»: a new trip built on the parent, flown the other
     way (owner's request 2026-09-06). A carrier who flies Dubai → New York
     almost always comes back, and the return listing is the outbound one with
     the route reversed and the dates unknown — everything else is the same
     person with the same suitcase.

     A **new** trip, not an edit: it publishes with POST and gets its own id.
     The marker is dropped from the URL once it has been used, so a reload
     continues the autosaved draft instead of overwriting what the carrier has
     since typed.

     It does replace an unfinished draft, and that was weighed: the wizard holds
     one draft, and pressing «Обратный рейс» is an unambiguous request for a
     specific one. Asking first would put a modal on the happy path to save a
     scratch form the carrier had already walked away from. */
  /* T3.11.16 — «повторить» rides the same effect. Both start from an existing
     trip with the dates cleared; the only difference is whether the route is
     turned around, and that is one call. Two effects would have been the same
     twenty lines twice, and the copy that fell behind would be the rarer one.

     They stay two buttons and two parameters, though, because the intentions
     are different and so are the numbers behind them: repeating a route is
     5.4 % of this market, holding a listing at the top is 60.8 %. Recording one
     as the other would make the first measurement of either useless. */
  useEffect(() => {
    const sourceId = reverseId ?? repeatId
    if (!sourceId || reversedFrom.current === sourceId) return
    const shape = (trip: Trip) => {
      const base = draftFromTrip(trip, prefs.toUnit, false)
      return { ...EMPTY, ...(reverseId ? reversedDraft(base) : base) }
    }
    const passed = (location.state as { trip?: Trip } | null)?.trip
    const drop = () => setParams({ step: '1' }, { replace: true })
    if (passed && passed.id === sourceId) {
      reversedFrom.current = sourceId
      setDraft(shape(passed))
      drop()
      return
    }
    // Cold load: the panel was opened, then the page reloaded. Same fallback as
    // the edit path — the carrier's own listing is the only place that returns
    // a trip of any status.
    listTrips({ carrier_id: user?.id, status: 'all', limit: 100 })
      .then(({ data }) => {
        const found = data.items.find((x) => x.id === sourceId)
        if (!found) {
          setError(t('trips.editNotFound') as string)
          return
        }
        reversedFrom.current = sourceId
        setDraft(shape(found))
        drop()
      })
      .catch(() => setError(t('trips.editNotFound') as string))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reverseId, repeatId])

  // Postal services follow the **arrival** country: onward shipping happens
  // after landing. Refetched when that country changes and not before — a
  // carrier editing the second leg has not changed where the parcel ends up.
  const arrivalIso = draft.nodes[draft.nodes.length - 1]?.country ?? ''
  useEffect(() => {
    if (!arrivalIso) {
      setPostal([])
      return
    }
    listPostalServices(arrivalIso)
      .then(({ data }) => setPostal(data))
      .catch(() => setPostal([]))
  }, [arrivalIso])

  // Payment systems follow both ends, arrival first.
  const departureIso = draft.nodes[0]?.country ?? ''
  useEffect(() => {
    if (!arrivalIso && !departureIso) {
      setSystems([])
      return
    }
    listPaymentSystems(arrivalIso || undefined, departureIso || undefined)
      .then(({ data }) => setSystems(data))
      .catch(() => setSystems([]))
  }, [arrivalIso, departureIso])

  /** T3.11.21 — «как в прошлый раз», without the dates.
   *
   *  Called by: the "same as last time" button on step 1.
   */
  const prefillFromLast = () => {
    if (!lastTrip) return
    setDraft((prev) => ({ ...prev, ...draftFromTrip(lastTrip, prefs.toUnit, false) }))
    setPrefilled(true)
  }

  // T3.11.07 — the route is edited by index; the three helpers exist so no
  // caller has to copy the array by hand and get the splice wrong.
  const patchNode = useCallback((index: number, delta: Partial<NodeDraft>) => {
    setDraft((prev) => ({
      ...prev,
      nodes: prev.nodes.map((node, i) => (i === index ? { ...node, ...delta } : node)),
    }))
  }, [])

  /** Insert a transfer directly before the destination.
   *
   *  There before, not after: a transfer is a stop on the way to where the
   *  carrier is going, and appending would move the destination one place
   *  further from the end every time. Adding one turns one flight into two
   *  without the carrier retyping either city.
   */
  const addTransfer = useCallback(() => {
    setDraft((prev) => {
      if (prev.nodes.length >= MAX_NODES) return prev
      // Guarded here as well as in the button's `disabled`: a disabled control
      // is a hint, not a rule, and this one is also reachable by keyboard.
      const ready = prev.nodes.every((node, i) =>
        isNodeComplete(node, i === prev.nodes.length - 1),
      )
      if (!ready) return prev
      const nodes = [...prev.nodes]
      nodes.splice(nodes.length - 1, 0, { ...EMPTY_NODE })
      return { ...prev, nodes }
    })
  }, [])

  /** Remove a transfer. Only the middle ones: an origin and a destination are
   *  what a route *is*, and a button that could delete them would leave a form
   *  with no way back to a publishable state. */
  const removeTransfer = useCallback((index: number) => {
    setDraft((prev) => {
      if (index <= 0 || index >= prev.nodes.length - 1) return prev
      return { ...prev, nodes: prev.nodes.filter((_, i) => i !== index) }
    })
  }, [])

  // T3.11.07 — the two ends are edited through one helper so the cell can be
  // written once and rendered twice. A computed key straight into `patch` would
  // widen to an index signature and need a cast to get back to `Draft`.
  const patchHandover = useCallback(
    (
      field: 'handoverOrigin' | 'handoverDestination',
      delta: Partial<HandoverDraft>,
    ) => {
      setDraft((prev) => ({ ...prev, [field]: { ...prev[field], ...delta } }))
    },
    [],
  )

  const validate = (): string | null => {
    // T3.11.07 — checked as flights, because that is what the API stores and
    // what the rules are about ("a city cannot fly to itself", "the second
    // departure is after the first"). The carrier typed stops; the legs are
    // derived from them, so the two can never disagree here.
    for (const [index, leg] of nodesToLegs(draft.nodes).entries()) {
      const at = { n: index + 1 }
      if (!leg.origin || !leg.destination) {
        return t('trips.newTripValidation.legRoute', at) as string
      }
      if (leg.origin === leg.destination) {
        return t('trips.newTripValidation.legSameRoute', at) as string
      }
      if (!leg.departAt) return t('trips.newTripValidation.legDate', at) as string
      const departure = new Date(leg.departAt)
      if (Number.isNaN(departure.getTime())) {
        return t('trips.newTripValidation.legDate', at) as string
      }
      // Only the first flight has to be ahead of now: a chain published on the
      // day of departure is 11.8 % of this market, and the later legs are
      // constrained by the one before them rather than by the clock.
      if (index === 0 && departure.getTime() < Date.now()) {
        return t('trips.newTripValidation.pastDate') as string
      }
      // T3.11.07 — the landing, when it is stated. Checked here as well as on
      // the server so the carrier reads it in their own words rather than as a
      // 422 from the publish button.
      if (leg.arriveAt) {
        const arrival = new Date(leg.arriveAt)
        if (Number.isNaN(arrival.getTime()) || arrival < departure) {
          return t('trips.newTripValidation.arrivalBeforeDeparture', at) as string
        }
      }
      const previous = nodesToLegs(draft.nodes)[index - 1]
      if (previous?.departAt && departure < new Date(previous.departAt)) {
        return t('trips.newTripValidation.legOutOfOrder', at) as string
      }
    }
    // T3.11.07 — weight is no longer required: the route is the whole of what a
    // carrier must state to be findable, and 31 % of this market publishes
    // inside two days of the flight. It is still checked when given, because a
    // typo there is a wrong claim rather than a missing one.
    if (draft.capacity) {
      const cap = parseFloat(draft.capacity)
      // Compared in kilograms: 0.5 kg is the floor the API enforces, and in
      // pounds the same number would be a different, smaller parcel.
      if (Number.isNaN(cap) || prefs.toKg(cap) < 0.5) {
        return t('trips.newTripValidation.capacity') as string
      }
    }
    return null
  }

  /** T3.11.07 — what publishing needs on top of what step 1 needs.
   *
   *  The settlement model became obligatory on 2026-09-08 and lives on step 3,
   *  which is skippable. Kept out of `validate` on purpose: that one gates
   *  *moving on*, and refusing step 2 over an answer that lives on step 3 would
   *  be a form blocking somebody for not having done a thing it has not offered
   *  them yet. So the express path survives — route and date are still the whole
   *  of a publishable trip — and publishing costs one tap on one of three chips.
   *
   *  Not defaulted for them. Pre-selecting «наличными» would be the platform
   *  answering a money question on a carrier's behalf, and a carrier publishing
   *  from step 1 would never see what had been answered for them.
   *
   *  Called by: `handleSubmit`. */
  const validateForPublish = (): string | null => {
    const problem = validate()
    if (problem) return problem
    if (!draft.paymentModel) {
      return t('trips.newTripValidation.paymentModel') as string
    }
    return null
  }

  const [preflightNotes, setPreflightNotes] = useState<RouteNote[]>([])
  const [ackedPreflight, setAckedPreflight] = useState(false)
  const preflightRef = useRef<HTMLDivElement>(null)

  // An overlay announced itself by covering the screen; a panel has to be
  // taken to. Without this the carrier presses publish, nothing visibly
  // happens, and the reason is a screen below the fold.
  useEffect(() => {
    if (preflightNotes.length === 0) return
    preflightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    preflightRef.current?.focus()
  }, [preflightNotes])

  /** T3.11.20 — moving on. Validation runs here and not on blur: a field that
   *  turns red while it is being typed into reads as nagging, and the only step
   *  with required answers is the first.
   *
   *  Called by: the "Next" button in the sheet footer. */
  const goNext = () => {
    if (step === 1) {
      const problem = validate()
      if (problem) {
        setError(problem)
        return
      }
    }
    setError('')
    goToStep(Math.min(TOTAL_STEPS, step + 1))
  }

  /** Leaving. The draft is already in `localStorage` on every keystroke, so the
   *  question is whether to keep it, not whether to save it — and the wrong
   *  silent answer is the one that throws away a half-filled form.
   *
   *  Called by: the close button in the sheet header, and Escape. */
  const requestClose = () => {
    // T3.11.07 — an edit has no draft to keep, so there is nothing to ask
    // about: the question «сохранить черновик?» would be about a thing that was
    // never written.
    if (editingId) {
      navigate(-1)
      return
    }
    const untouched =
      draft.nodes.length === 2 && draft.nodes.every((n) => !n.code && !n.departAt)
    if (untouched) {
      localStorage.removeItem(DRAFT_KEY)
      navigate(-1)
      return
    }
    setAskingToClose(true)
  }

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setError('')
    const validationError = validateForPublish()
    if (validationError) {
      setError(validationError)
      // The answer that is missing is almost always the settlement model, and
      // it is on a screen the carrier may never have opened. Taking them there
      // beats a message about a chip they cannot see.
      if (!draft.paymentModel) goToStep(3)
      return
    }
    // T3.11.07 — the "over 15 kg is unusual for hand luggage" confirmation is
    // gone. The scale now runs to 32, because 23 kg is an ordinary checked bag
    // and 32 the airline ceiling for one; asking a carrier to confirm the most
    // common answer on the market was the prompt teaching people to click
    // through prompts.
    //
    // T_UX.2 pt.3 — pre-flight warning for complex/restricted corridors.
    // T3.11.07 — asked for **every** leg, not just the endpoints. A chain
    // through Istanbul is subject to Turkish transit rules, and PRD §3.11.1 is
    // explicit that the transit node is present in the main corridor always
    // rather than occasionally: checking only first-to-last would skip the leg
    // most likely to carry a restriction.
    if (!ackedPreflight) {
      try {
        const perLeg = await Promise.all(
          nodesToLegs(draft.nodes).map((leg) =>
            listRouteNotes({ origin: leg.origin, destination: leg.destination }),
          ),
        )
        // A corridor flown twice (there and back) would otherwise warn twice
        // about the same thing, so the notes are collected by id.
        const byId = new Map<string, RouteNote>()
        for (const note of perLeg.flatMap((r) => r.data)) {
          if (note.status === 'complex' || note.status === 'restricted') {
            byId.set(note.id, note)
          }
        }
        const critical = [...byId.values()]
        if (critical.length > 0) {
          setPreflightNotes(critical)
          return
        }
      } catch {
        // fall through — never block publish on notes fetch failure
      }
    }
    setLoading(true)
    try {
      const payload: CreateTripPayload = {
        // T3.11.07 — the route travels as the chain the carrier typed. Order is
        // the array order; the server assigns it and derives the trip's
        // origin, destination and date from the first and last leg.
        legs: nodesToLegs(draft.nodes).map((leg) => ({
          origin: leg.origin,
          destination: leg.destination,
          depart_at: leg.departAt,
          // Empty stays null: a landing time nobody stated is not one to invent,
          // and the column keeps the two apart.
          arrive_at: leg.arriveAt || null,
          // One answer for the trip, written onto every leg. The model keeps it
          // per leg so a chain flown by two people stays expressible later.
          flown_by: draft.flownBy,
        })),
        // Empty means "not stated" and travels as `null`: the express path made
        // weight optional, and a zero here would be a claim nobody made.
        // Typed in the account's unit, stored metric: the column is kilograms
        // and a pound written into it would be a weight nobody meant.
        capacity: draft.capacity ? prefs.toKg(Number(draft.capacity)) : null,
        allowed_categories: draft.categories,
        // Empty stays empty: a trip without a stated price is "price on
        // request", not a trip priced at zero.
        price_per_kg: draft.pricePerKg ? Number(draft.pricePerKg) : null,
        min_deal_price: draft.minDealPrice ? Number(draft.minDealPrice) : null,
        // Empty means "the account's default", chosen once in the profile.
        currency: draft.currency || prefs.currency,
        max_declared_value: draft.maxDeclaredValue
          ? Number(draft.maxDeclaredValue)
          : null,
        // Empty means "the same money the trip is priced in" and travels as
        // null: writing the trip's currency here would record a choice the
        // carrier never made and freeze it if they later re-price.
        max_declared_value_currency: draft.maxDeclaredValueCurrency || null,
        // T3.11.07 — the two capacities and the two ends of the handover.
        // `sizeHint` empty stays null: "did not say" and "small" are different
        // answers and the API keeps them apart.
        space_kind: draft.spaceKind,
        size_hint: draft.sizeHint || null,
        handover_origin: toHandover(draft.handoverOrigin),
        handover_destination: toHandover(draft.handoverDestination),
        // Nothing ticked is `null`, not `[]`: "said nothing" and "considered it
        // and excludes nothing" are different answers, and the card reads them
        // differently.
        excluded: draft.excluded.length > 0 ? draft.excluded : null,
        services: draft.services.length > 0 ? draft.services : null,
        // T3.11.07 — obligatory since 2026-09-08. The publish guard refuses
        // before this runs, so `null` cannot leave the form; kept as a fallback
        // rather than a cast, because a `!` here would turn a guard somebody
        // later loosens into a 422 nobody can read.
        payment_model: draft.paymentModel || null,
        // Only meaningful beside e-money: cash has no system to name and the
        // wallet is the system, so the server refuses one sent with either.
        payment_systems:
          draft.paymentModel === EMONEY_MODEL
            ? splitChips(draft.paymentSystems)
            : null,
        // T_UX.15 — sent explicitly so an emptied field means "this trip has no
        // rules" rather than "fall back to my template".
        carriage_rules: draft.carriageRules,
      }
      /* T3.11.07 — the same row when editing, a new one otherwise. Cancel and
         republish would have been fewer lines and changes the id — which is
         what every inquiry, deal and Nostr event points at, so a carrier fixing
         a departure hour would orphan the conversation about it. */
      const saved = editingId
        ? await updateTrip(editingId, payload)
        : await createTrip(payload)
      // Only a publication clears the draft: an edit never wrote to it.
      if (!editingId) localStorage.removeItem(DRAFT_KEY)
      /* T3.11.07 — straight to the card that was just written, not to the top
         of the board (owner's request 2026-09-06). The id goes in the query
         string: the board rings it and scrolls to it, and a reload keeps it. */
      navigate(`/trips?trip=${saved.data.id}`)
    } catch {
      setError(t('trips.publishError') as string)
    } finally {
      setLoading(false)
    }
  }

  // Cmd/Ctrl+Enter shortcut → publish
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault()
        handleSubmit()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  const showHookIcon = (
    icon: string,
    label: string,
    enabled: boolean,
  ) => (
    <button
      type="button"
      onClick={() => {
        if (!enabled) {
          alert(t('trips.newTripHookComingSoon', { feature: label }) as string)
        }
      }}
      disabled={!enabled}
      title={label}
      aria-label={label}
      className={`w-10 h-10 rounded-field border transition-colors ${
        enabled
          ? 'border-cyan/40 text-cyan hover:bg-cyan/10'
          : 'border-navy/10 text-navy/30 cursor-not-allowed'
      }`}
    >
      <span aria-hidden="true" className="text-lg">
        {icon}
      </span>
    </button>
  )

  if (!user?.can_carry) {
    return (
      <div className="text-center py-24">
        <p className="text-sm font-body text-navy/40">{t('trips.carriersOnly')}</p>
      </div>
    )
  }

  // The two ends of the chain, named on the handover cell so "where you accept"
  // is not an abstract question. Empty until the carrier has typed the route.
  const firstOrigin = draft.nodes[0]?.code ?? ''
  const lastDestination = draft.nodes[draft.nodes.length - 1]?.code ?? ''
  /** Every stop named, and every one but the last given a departure. Gates the
   *  "add a transfer" button: offering a fourth empty box while the second is
   *  blank shows work instead of asking for it. */
  const routeAnswered = draft.nodes.every((node, i) =>
    isNodeComplete(node, i === draft.nodes.length - 1),
  )
  /** T3.11.07 — the profile lists, narrowed to one end of the route (owner's
   *  decision 2026-09-06).
   *
   *  A row with no country is kept rather than dropped: `null` means «anywhere»
   *  — «наличные при встрече» genuinely is, and so is every row written before
   *  the field existed. Dropping those would have made the retrofit lossy for
   *  people who did nothing wrong.
   *
   *  An **unknown** end also keeps everything. The country is only known once
   *  an airport is picked from the list rather than typed; filtering on an empty
   *  ISO would empty the picker and read as "you have no meeting places", which
   *  is a different and untrue statement.
   */
  const placesFor = (iso: string) =>
    places.filter((p) => !iso || !p.country_iso || p.country_iso === iso)
  const methodsFor = (iso: string) =>
    (user?.payment_methods ?? []).filter(
      (m) => !iso || !m.country || m.country === iso,
    )

  /** T3.11.07 — the ways this carrier said they can be paid, kept once in the
   *  profile and narrowed to this route. Offered above the corridor catalogue:
   *  that catalogue knows what exists in a country, this knows what this person
   *  actually accepts.
   *
   *  Both ends, deduplicated by name: money moves between two countries and the
   *  carrier may be paid at either, so a method filed under one of them belongs
   *  on the list — and one filed under both must not appear twice.
   *
   *  Declared after `methodsFor` on purpose: a `const` referenced above its own
   *  declaration is a temporal-dead-zone crash at first render, not a warning. */
  const myMethods = [
    ...new Set([
      ...methodsFor(arrivalIso).map((m) => m.name),
      ...methodsFor(departureIso).map((m) => m.name),
    ]),
  ]
  // T3.11.07 — the weight scale in the unit this account reads in. Storage
  // stays metric; only the numbers on screen change.
  const scale = CAPACITY_SCALE[prefs.unit]

  // T3.11.07 — through `usePrefs`, not `toLocaleString` on the spot. The clock
  // format is an account setting, not a consequence of the interface language:
  // a Russian-speaking carrier working a US corridor reads the hours their
  // paperwork uses. Calling the locale directly here is the exact bug that hook
  // was written to end, and this file had a copy of it.
  const formatDeparture = (value: string) => (value ? prefs.dateTime(value) : '—')


  /** The card as it will appear on the board.
   *
   *  T3.11.20 — collapsed, and present from the first step rather than as a
   *  fifth one. Carriers are used to seeing their whole post before it goes
   *  out; a wizard that hides it until the end leaves the feeling that
   *  something was dropped along the way. A step of its own would have cost
   *  every carrier a screen, including the 31 % publishing inside two days.
   */
  const preview = (
    <details className="rounded-card border border-navy/10 bg-navy/[0.02] px-4 py-3">
      <summary className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide cursor-pointer">
        {t('trips.newTripCell.preview')}
      </summary>
      <div className="mt-3 bg-white rounded-card border border-navy/10 p-4">
        <div className="space-y-1">
          {nodesToLegs(draft.nodes).map((leg, index) => (
            <div
              key={index}
              className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-2"
            >
              <MonoText className="text-lg text-navy font-medium">
                {routeNode(leg.origin || '???', leg.originCity)} →{' '}
                {routeNode(leg.destination || '???', leg.destinationCity)}
              </MonoText>
              <MonoText className="text-sm text-navy/60">
                {formatDeparture(leg.departAt)}
                {/* The landing, when the carrier stated one. Only the last stop
                    is ever asked, so this shows on one row of the chain. */}
                {leg.arriveAt && ` → ${formatDeparture(leg.arriveAt)}`}
              </MonoText>
            </div>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
          {draft.capacity && (
            <span>
              {t('trips.capacity')}:{' '}
              <MonoText className="text-xs">
                {prefs.weight(prefs.toKg(Number(draft.capacity)))}
              </MonoText>
              {draft.spaceKind !== 'unspecified' && (
                <span className="ml-1">
                  · {t(`trips.spaceKind.${draft.spaceKind}`)}
                </span>
              )}
            </span>
          )}
          {draft.sizeHint && <span>{t(`trips.sizeHint.${draft.sizeHint}`)}</span>}
          {draft.flownBy === 'proxy' && (
            <span>{t('trips.flownBy.proxyChip')}</span>
          )}
          {/* Zero free allowance is the one number a sender has to see before
              writing: the bag is not full, but a valuable parcel is not what
              this flight can take. */}
          {draft.maxDeclaredValue !== '' && Number(draft.maxDeclaredValue) === 0 && (
            <span className="text-amber">{t('trips.customsNoneLeft')}</span>
          )}
          {draft.excluded.length > 0 && (
            <span className="text-amber">
              {t('trips.excludedPrefix')}{' '}
              {draft.excluded.map((x) => t(`trips.excluded.${x}`)).join(', ')}
            </span>
          )}
          {draft.categories.length > 0 && (
            <span className="flex flex-wrap gap-1">
              {draft.categories.map((c) => (
                <span
                  key={c}
                  className="text-xs font-mono bg-ivory px-2 py-0.5 rounded text-navy/60"
                >
                  {t(`categories.${c}`, { defaultValue: c })}
                </span>
              ))}
            </span>
          )}
        </div>
      </div>
    </details>
  )

  const stepTitles = [
    t('trips.wizard.step1'),
    t('trips.wizard.step2'),
    t('trips.wizard.step3'),
    t('trips.wizard.step4'),
  ]
  const stepSubtitles = [
    t('trips.wizard.step1Sub'),
    t('trips.wizard.optional'),
    t('trips.wizard.optional'),
    t('trips.wizard.optional'),
  ]

  const publishButton = (primary: boolean) => (
    <button
      type="button"
      onClick={() => handleSubmit()}
      disabled={loading}
      className={
        primary
          ? 'bg-amber text-white font-display font-semibold px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity disabled:opacity-50'
          : 'border border-amber/60 text-amber font-display font-medium px-4 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-amber/5 transition-colors disabled:opacity-50'
      }
    >
      {loading
        ? t('common.loading')
        : editingId
          ? t('common.save')
          : t('trips.publish')}
    </button>
  )

  return (
    <WizardSheet
      step={step}
      total={TOTAL_STEPS}
      /* T3.11.07 — an edit says so in the header. Four identical steps that
         quietly rewrite an existing listing instead of making a new one is the
         kind of mode a person only discovers by pressing the button. */
      title={
        editingId
          ? (t('trips.preview.edit') as string)
          : (stepTitles[step - 1] as string)
      }
      subtitle={stepSubtitles[step - 1] as string}
      onBack={step > 1 ? () => goToStep(step - 1) : undefined}
      onClose={requestClose}
      footer={
        <>
          {/* T3.11.07 — publish is reachable from the first step, not the
              second. `0060` made weight optional precisely so a route and a
              date would be a publishable trip: the median carrier on this
              market posts five days out, 31 % inside two days and 11.8 % on
              the day of the flight, and a screen standing between them and the
              board is the toll that migration removed. */}
          {publishButton(step === TOTAL_STEPS)}
          {step < TOTAL_STEPS && (
            <button
              type="button"
              onClick={goNext}
              className="bg-navy text-ivory font-display font-semibold px-5 py-3 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid transition-colors"
            >
              {t('common.continue')}
            </button>
          )}
        </>
      }
    >
      {askingToClose && (
        <div
          role="alertdialog"
          aria-labelledby="close-title"
          className="rounded-card border-2 border-navy/20 bg-ivory p-4 space-y-3"
        >
          <p
            id="close-title"
            className="font-display font-semibold text-sm text-navy"
          >
            {t('trips.wizard.keepDraftTitle')}
          </p>
          <p className="text-xs font-body text-navy/60">
            {t('trips.wizard.keepDraftBody')}
          </p>
          <div className="flex flex-wrap gap-2 justify-end">
            <button
              type="button"
              onClick={() => setAskingToClose(false)}
              className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2 min-h-[2.75rem]"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={() => {
                localStorage.removeItem(DRAFT_KEY)
                navigate(-1)
              }}
              className="text-sm font-body text-danger hover:opacity-80 px-3 py-2 min-h-[2.75rem]"
            >
              {t('trips.wizard.discardDraft')}
            </button>
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="bg-navy text-ivory font-display font-medium px-4 py-2 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid"
            >
              {t('trips.wizard.keepDraft')}
            </button>
          </div>
        </div>
      )}

      {/* ── Step 1 · where and when ─────────────────────────────────────── */}
      {step === 1 && (
        <>
          {/* T3.11.21 — offered only while the form is untouched. A carrier who
              has begun typing is not shown a button that would overwrite it,
              and one who has already used it is not shown it twice. */}
          {/* Never in edit mode: a button that overwrites the trip being edited
              with a different one is the opposite of what it says. */}
          {!editingId &&
            lastTrip &&
            !prefilled &&
            !draft.nodes[0].code &&
            !draft.nodes[0].departAt && (
            <button
              type="button"
              onClick={prefillFromLast}
              className="w-full border border-cyan/40 bg-cyan/5 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy hover:bg-cyan/10 transition-colors text-left"
            >
              <span className="font-display font-semibold">
                {t('trips.sameAsLast')}
              </span>
              <MonoText className="ml-2 text-xs text-navy/50">
                {lastTrip.origin} → {lastTrip.destination}
              </MonoText>
              <span className="block text-[11px] font-body text-navy/50 mt-0.5">
                {t('trips.sameAsLastHint')}
              </span>
            </button>
          )}

          <div className="flex items-center justify-between gap-3">
            <p className="text-[11px] font-body text-navy/40">
              {t('trips.routeHint')}
            </p>
            <div className="flex gap-2 shrink-0">
              {/* EXP-03 / EXP-04 hook points. Second rework of this form in one
                  phase, and §3.10.1 requires them to survive both. */}
              {showHookIcon('🎤', t('trips.newTripHook.voice'), VOICE_ENABLED)}
              {showHookIcon('📷', t('trips.newTripHook.scan'), SCAN_ENABLED)}
            </div>
          </div>

          {/* T3.11.07 — stops, not flights (owner's decision 2026-09-06).
              The carrier names where they start, where they are going, and any
              transfer in between; the hops fall out of that. Istanbul is typed
              once instead of twice — as an arrival and again as a departure —
              and so it can no longer disagree with itself. */}
          <ol className="space-y-2">
            {draft.nodes.map((node, index) => {
              const isFirst = index === 0
              const isLast = index === draft.nodes.length - 1
              const role = isFirst ? 'from' : isLast ? 'to' : 'transfer'
              return (
                <li
                  key={index}
                  className={`rounded-field border p-3 space-y-3 ${
                    role === 'transfer'
                      ? 'border-cyan/30 bg-cyan/[0.03]'
                      : 'border-navy/10'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <label
                      htmlFor={`${stopId}-${index}`}
                      className="text-xs font-body font-medium text-navy/60"
                    >
                      {t(`trips.stop.${role}`)}
                    </label>
                    {/* Only a transfer can be removed. An origin and a
                        destination are what a route is; a button that could
                        delete them would leave a form with no way back to a
                        publishable state. */}
                    {role === 'transfer' && (
                      <button
                        type="button"
                        onClick={() => removeTransfer(index)}
                        className="text-[11px] font-body text-navy/40 hover:text-danger transition-colors"
                      >
                        {t('trips.removeTransfer')}
                      </button>
                    )}
                  </div>
                  <AirportSelect
                    inputId={`${stopId}-${index}`}
                    value={node.code}
                    onChange={(v) => patchNode(index, { code: v })}
                    onPick={(a) =>
                      patchNode(index, { country: a.country_iso, city: a.city })
                    }
                    required
                    placeholder={isLast ? 'JFK' : 'DXB'}
                  />
                  {/* The last stop has no departure — nobody leaves the place
                      they are going to. Time is part of the answer rather than
                      a tail on the date: 29.8 % of real posts state the hour,
                      and the handover window is counted back from it. */}
                  {!isLast && (
                    <div>
                      <label
                        htmlFor={`${departId}-${index}`}
                        className="block text-[11px] font-body text-navy/40 mb-1"
                      >
                        {node.code
                          ? t('trips.departureFrom', { code: node.code })
                          : t('trips.newTripCell.date')}
                      </label>
                      {/* T3.11.07 — our own picker, not `datetime-local`. The
                          native one takes 12- or 24-hour from the **device**
                          locale with no attribute to override it, so an account
                          set to "European" still read `02:30 PM` inside the
                          calendar — the setting looked broken because it was
                          honoured everywhere except the one control people
                          actually use. */}
                      <DateTimeField
                        id={`${departId}-${index}`}
                        value={node.departAt}
                        onChange={(v) => patchNode(index, { departAt: v })}
                        style={prefs.style}
                        /* Each departure is after the one before it, so the
                           calendar cannot offer a day that would fail
                           validation two clicks later. */
                        min={index > 0 ? draft.nodes[index - 1].departAt : undefined}
                        required
                      />
                    </div>
                  )}
                  {/* T3.11.07 — the landing (owner's decision 2026-09-06), and
                      only at the end of the route. That is the time a sender
                      needs: when the parcel can actually be collected. Asking it
                      at every transfer would be asking a carrier to look up
                      three flight schedules to publish one trip.

                      Optional, and it says so: 29.8 % of real posts state a
                      departure hour at all, so a landing time many carriers do
                      not know is not one to make them invent. */}
                  {isLast && (
                    <div>
                      <label
                        htmlFor={`${arriveId}-${index}`}
                        className="block text-[11px] font-body text-navy/40 mb-1"
                      >
                        {node.code
                          ? t('trips.arrivalAt', { code: node.code })
                          : t('trips.arrival')}{' '}
                        <span className="text-navy/30">{t('trips.optional')}</span>
                      </label>
                      <DateTimeField
                        id={`${arriveId}-${index}`}
                        value={node.arriveAt}
                        onChange={(v) => patchNode(index, { arriveAt: v })}
                        style={prefs.style}
                        /* It cannot land before the last flight left. The
                           calendar refuses the day rather than letting the
                           carrier find out from a validation message. */
                        min={draft.nodes[index - 1]?.departAt}
                      />
                    </div>
                  )}
                </li>
              )
            })}
          </ol>

          {/* A transfer is offered only once the route is answered: handing out
              empty rows in advance shows work nobody asked for. */}
          {draft.nodes.length < MAX_NODES && (
            <button
              type="button"
              onClick={addTransfer}
              disabled={!routeAnswered}
              title={routeAnswered ? undefined : (t('trips.addTransferBlocked') as string)}
              className="w-full border border-dashed border-navy/25 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy/60 hover:border-cyan hover:text-navy transition-colors disabled:opacity-40 disabled:hover:border-navy/25 disabled:hover:text-navy/60 disabled:cursor-not-allowed"
            >
              {t('trips.addTransfer')}
            </button>
          )}

          {/* Who is flying — one answer for the trip, not one per flight, and a
              switch rather than two buttons (owner's decision 2026-09-06).
              Both positions are spelled out beside it: this is the claim the
              market makes most often and backs least, so neither state may be
              the one nobody read. */}
          <div className="flex items-center justify-between gap-3 border-t border-navy/10 pt-3">
            <span className="text-xs font-body font-medium text-navy/60">
              {t('trips.flownBy.label')}
            </span>
            <label className="flex items-center gap-3 cursor-pointer">
              <span
                className={`text-xs font-body ${
                  draft.flownBy === 'self' ? 'text-navy' : 'text-navy/40'
                }`}
              >
                {t('trips.flownBy.self')}
              </span>
              <span className="relative inline-flex">
                <input
                  type="checkbox"
                  role="switch"
                  checked={draft.flownBy === 'proxy'}
                  onChange={(e) =>
                    patch({ flownBy: e.target.checked ? 'proxy' : 'self' })
                  }
                  className="peer sr-only"
                />
                <span
                  aria-hidden="true"
                  className="w-11 h-6 rounded-full bg-navy/15 peer-checked:bg-cyan transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-cyan peer-focus-visible:ring-offset-2"
                />
                <span
                  aria-hidden="true"
                  className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5"
                />
              </span>
              <span
                className={`text-xs font-body ${
                  draft.flownBy === 'proxy' ? 'text-navy' : 'text-navy/40'
                }`}
              >
                {t('trips.flownBy.proxy')}
              </span>
            </label>
          </div>
        </>
      )}

      {/* ── Step 2 · what you carry and how much room ───────────────────── */}
      {step === 2 && (
        <>
          <div className="space-y-2">
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('trips.newTripCell.categories')}
            </p>
            <CategoryBubbles
              selected={draft.categories}
              onChange={(next) => patch({ categories: next })}
            />
          </div>

          <div className="space-y-3 border-t border-navy/10 pt-4">
            <label
              id={capacityLabelId}
              htmlFor={capacityId}
              className="block text-xs font-display font-semibold text-navy/50 uppercase tracking-wide"
            >
              {t('trips.newTripCell.capacity')}
            </label>
            <p className="text-[11px] font-body text-navy/40 -mt-1">
              {t('trips.spaceHint')}
            </p>
            <div className="flex flex-wrap gap-2">
              {SPACE_KINDS.map((kind) => (
                <button
                  key={kind}
                  type="button"
                  aria-pressed={draft.spaceKind === kind}
                  onClick={() =>
                    patch({
                      spaceKind: draft.spaceKind === kind ? 'unspecified' : kind,
                    })
                  }
                  className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
                    draft.spaceKind === kind
                      ? 'border-cyan bg-cyan/10 text-navy'
                      : 'border-navy/20 text-navy/50 hover:border-navy/40'
                  }`}
                >
                  {t(`trips.spaceKind.${kind}`)}
                </button>
              ))}
            </div>
            {/* T3.11.07 — the number and the suitcase size on one line (owner's
                decision 2026-09-06). They are two ways of answering the same
                question — "how much room" — and stacking them made the second
                read as a further question rather than as the alternative it is.
                Kilograms are named in 2.4 % of real posts and "small / not big"
                in 9.9 %, so the qualitative half is the one more carriers use.
                The size is chosen once: it is a radio group, not chips. */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <div className="flex items-baseline gap-2">
                <input
                  id={capacityId}
                  type="number"
                  step="0.5"
                  min="0"
                  max={scale.max}
                  value={draft.capacity}
                  onChange={(e) => patch({ capacity: e.target.value })}
                  placeholder="23"
                  className="w-20 border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-lg font-mono text-navy focus:outline-none focus:border-cyan"
                />
                <MonoText className="text-sm text-navy/60">{prefs.unit}</MonoText>
              </div>
              <fieldset className="flex flex-wrap items-center gap-2">
                <legend className="sr-only">{t('trips.sizeHint.label')}</legend>
                {SIZE_HINTS.map((size) => (
                  <label
                    key={size}
                    className={`text-xs font-body px-3 py-2 min-h-[2.75rem] flex items-center rounded-field border cursor-pointer transition-colors ${
                      draft.sizeHint === size
                        ? 'border-cyan bg-cyan/10 text-navy'
                        : 'border-navy/20 text-navy/50 hover:border-navy/40'
                    }`}
                  >
                    <input
                      type="radio"
                      name="sizeHint"
                      value={size}
                      checked={draft.sizeHint === size}
                      onChange={() => patch({ sizeHint: size })}
                      className="sr-only"
                    />
                    {t(`trips.sizeHint.${size}`)}
                  </label>
                ))}
              </fieldset>
            </div>
            <div>
              <input
                type="range"
                aria-labelledby={capacityLabelId}
                min="0"
                max={scale.max}
                step="0.5"
                value={draft.capacity || 0}
                onChange={(e) =>
                  // Zero on the scale is "not stated", not "nothing fits": the
                  // field is optional, and `null` is what the API stores for it.
                  patch({ capacity: e.target.value === '0' ? '' : e.target.value })
                }
                className="capacity-slider"
              />
              {/* A ruler, not a caption. Every kilogram gets a tick so 7 is
                  findable by eye; only the eight numbers people actually say
                  are printed, because labelling all 33 hides the eight.

                  T3.11.07 — inset by half a thumb on each side (`.capacity-ruler`,
                  owner's decision 2026-09-06). The thumb's centre never reaches
                  either edge of the track, so ticks laid out across the full
                  width put "0" left of where the handle can go and the ceiling
                  right of it — wrong exactly where a carrier checks it. */}
              <div
                aria-hidden="true"
                className="capacity-ruler relative h-7 mt-1 select-none"
              >
                {Array.from({ length: scale.max + 1 }, (_, mark) => {
                  const labelled = (scale.labelled as readonly number[]).includes(mark)
                  return (
                    <span
                      key={mark}
                      style={{ left: `${(mark / scale.max) * 100}%` }}
                      className="absolute top-0 -translate-x-1/2 flex flex-col items-center"
                    >
                      <span
                        className={
                          labelled ? 'w-px h-2 bg-navy/40' : 'w-px h-1 bg-navy/15'
                        }
                      />
                      {labelled && (
                        <span className="mt-0.5 text-[10px] font-mono text-navy/40">
                          {mark}
                        </span>
                      )}
                    </span>
                  )
                })}
              </div>
            </div>
          </div>

          {/* The customs allowance — the other capacity. A ceiling alone cannot
              say "spent", and "spent" is what carriers announce. */}
          <div className="space-y-3 border-t border-navy/10 pt-4">
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('trips.newTripCell.customs')}
            </p>
            <p className="text-[11px] font-body text-navy/40 -mt-1">
              {t('trips.customsHint')}
            </p>
            {/* T3.11.07 — the number is what is **left**, not a ceiling. It
                carried a separate `open / exhausted` state for a few hours;
                once the label says "free", zero already says "spent", and the
                second field was a second place for one fact to be wrong.

                Steps of 200 on the arrows and the wheel (owner's decision
                2026-09-06). Allowances are round: $2 000 into the US, and the
                figures carriers quote move in hundreds, not in ones. Typing
                stays free — `step` constrains the stepper, not the keyboard —
                so an exact 1 750 is still one field away. */}
            <div className="flex items-end gap-2">
              <label className="flex-1 min-w-[7rem]">
                <span className="block text-[11px] font-body text-navy/40 mb-1">
                  {t('trips.maxDeclaredValue')}
                </span>
                <input
                  type="number"
                  step={ALLOWANCE_STEP}
                  min="0"
                  value={draft.maxDeclaredValue}
                  onChange={(e) => patch({ maxDeclaredValue: e.target.value })}
                  /* The wheel is handled rather than left to the browser:
                     Chrome scrolls a focused number input and Firefox does not,
                     so half the carriers would find the wheel dead. Only while
                     focused, and the page scroll is left alone otherwise — a
                     field that eats the wheel in passing is the reason most
                     products disable this. */
                  onWheel={(e) => {
                    if (document.activeElement !== e.currentTarget) return
                    e.preventDefault()
                    const current = Number(draft.maxDeclaredValue || 0)
                    const next = Math.max(
                      0,
                      current + (e.deltaY < 0 ? ALLOWANCE_STEP : -ALLOWANCE_STEP),
                    )
                    patch({ maxDeclaredValue: String(next) })
                  }}
                  className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                />
              </label>
              {/* Its own currency, not the trip's. An allowance is denominated
                  by the country the parcel lands in — $2 000 into the US —
                  while the price is whatever the carrier quotes in, and one
                  shared field would mean picking the allowance's currency
                  silently re-prices the trip. Nothing chosen means "same as the
                  trip", which is the ordinary case. */}
              <label className="w-28 shrink-0">
                <span className="block text-[11px] font-body text-navy/40 mb-1">
                  {t('trips.allowanceCurrency')}
                </span>
                <select
                  value={draft.maxDeclaredValueCurrency}
                  onChange={(e) => patch({ maxDeclaredValueCurrency: e.target.value })}
                  className="w-full border border-navy/20 rounded-field px-2 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                >
                  <option value="">
                    {draft.currency || prefs.currency}
                  </option>
                  {CURRENCIES.map((code) => (
                    <option key={code} value={code}>
                      {code}
                    </option>
                  ))}
                </select>
              </label>
              {/* Premium, and said so plainly rather than shown as a working
                  button. `§9.1`: a control that looks live and is not is worse
                  than one that names its price. The feature itself is T6.1 —
                  it is where the corridor's real allowance gets fetched. */}
              <button
                type="button"
                disabled
                title={t('trips.customsAutofillPremium') as string}
                className="px-3 py-2 min-h-[2.75rem] rounded-field border border-navy/15 text-[11px] font-body text-navy/30 cursor-not-allowed shrink-0"
              >
                {t('trips.customsAutofill')} ★
              </button>
            </div>
          </div>
        </>
      )}

      {/* ── Step 3 · handover and settlement ────────────────────────────── */}
      {step === 3 && (
        <>
          <div className="space-y-3">
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('trips.newTripCell.handover')}
            </p>
            <p className="text-[11px] font-body text-navy/40 -mt-1">
              {t('trips.handoverHint')}
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {(
                [
                  /* T3.11.07 — each end carries its country, not just its code
                     (owner's decision 2026-09-06). The profile lists are filed
                     by country and the form filters on it: a Moscow meeting
                     place has no business being offered to somebody arriving in
                     Dubai, and a list that has to be read and rejected on every
                     publication is worse than no list. */
                  ['handoverOrigin', firstOrigin, departureIso] as const,
                  ['handoverDestination', lastDestination, arrivalIso] as const,
                ]
              ).map(([field, place, iso]) => (
                <fieldset
                  key={field}
                  className="border border-navy/10 rounded-field p-3 space-y-3"
                >
                  <legend className="px-1 text-[11px] font-mono text-navy/40">
                    {t(`trips.${field}`)}
                    {place && <span className="ml-1 text-cyan">{place}</span>}
                  </legend>
                  <div className="flex flex-wrap gap-2">
                    {HANDOVER_METHODS.map((method) => {
                      const chosen = draft[field].methods.includes(method)
                      return (
                        <button
                          key={method}
                          type="button"
                          aria-pressed={chosen}
                          onClick={() => {
                            const methods = chosen
                              ? draft[field].methods.filter((m) => m !== method)
                              : [...draft[field].methods, method]
                            /* T3.11.22 — dropping «по почте» drops the services
                               chosen under it. The server refuses the pair now
                               (naming CDEK while not posting anything is the
                               contradiction the task removes), and a draft that
                               kept them would send a body it knows will be
                               rejected — the person would be told they are
                               wrong about a box the form had already hidden. */
                            const losesPost =
                              chosen && method === 'local_post'
                            patchHandover(field, {
                              methods,
                              ...(losesPost ? { postalServices: '' } : {}),
                            })
                          }}
                          className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
                            chosen
                              ? 'border-cyan bg-cyan/10 text-navy'
                              : 'border-navy/20 text-navy/50 hover:border-navy/40'
                          }`}
                        >
                          {t(`cards.opt.${method}`)}
                        </button>
                      )
                    })}
                  </div>
                  {/* Each of the three below appears only when the method it
                      belongs to is chosen. That is the whole fix for the three
                      vocabularies (T3.11.22): the levels narrow — what I do,
                      how I hand over, which service — and a level that cannot
                      be answered before the one above it cannot contradict it.
                      An always-visible field teaches people to skip the block. */}

                  {/* Meeting in person — one of the places from the profile. */}
                  {draft[field].methods.includes('in_person') && (
                    <label className="block">
                      <span className="block text-[11px] font-body text-navy/40 mb-1">
                        {t('trips.meetingPlace')}
                      </span>
                      {placesFor(iso).length > 0 ? (
                        <select
                          value={draft[field].placeId}
                          onChange={(e) =>
                            patchHandover(field, { placeId: e.target.value })
                          }
                          className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
                        >
                          <option value="">{t('trips.pickNothing')}</option>
                          {placesFor(iso).map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.city ? `${p.city} · ${p.description}` : p.description}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <p className="text-[11px] font-body text-navy/40">
                          {t('trips.noMeetingPlaces')}
                        </p>
                      )}
                    </label>
                  )}

                  {/* Any method that involves an address — a courier collecting
                      it, a parcel sent, a locker booked against one. */}
                  {draft[field].methods.some((m) =>
                    ['courier', 'local_post', 'parcel_locker', 'poste_restante'].includes(m),
                  ) && (
                    <label className="block">
                      <span className="block text-[11px] font-body text-navy/40 mb-1">
                        {t('trips.handoverAddress')}
                      </span>
                      {addresses.length > 0 ? (
                        <select
                          value={draft[field].addressId}
                          onChange={(e) =>
                            patchHandover(field, { addressId: e.target.value })
                          }
                          className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
                        >
                          <option value="">{t('trips.pickNothing')}</option>
                          {addresses.map((a) => (
                            <option key={a.id} value={a.id}>
                              {a.label}
                              {a.city ? ` · ${a.city}` : ''}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <p className="text-[11px] font-body text-navy/40">
                          {t('trips.noAddresses')}
                        </p>
                      )}
                    </label>
                  )}

                  {/* The third level, destination end only: onward shipping
                      happens after landing. Local services of the arrival
                      country, and typing by hand for everything else — this
                      catalogue has no external source and must not be able to
                      say the one company collecting parcels in a carrier's town
                      does not exist. */}
                  {field === 'handoverDestination' &&
                    draft[field].methods.includes('local_post') && (
                      <div className="space-y-2">
                        {postal.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {postal.map((s) => {
                              const chosen = (
                                splitChips(draft[field].postalServices) ?? []
                              ).includes(s.name)
                              return (
                                <button
                                  key={s.code}
                                  type="button"
                                  aria-pressed={chosen}
                                  onClick={() => {
                                    const current =
                                      splitChips(draft[field].postalServices) ?? []
                                    const next = chosen
                                      ? current.filter((x) => x !== s.name)
                                      : [...current, s.name]
                                    patchHandover(field, {
                                      postalServices: next.join(', '),
                                    })
                                  }}
                                  className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
                                    chosen
                                      ? 'border-cyan bg-cyan/10 text-navy'
                                      : 'border-navy/20 text-navy/50 hover:border-navy/40'
                                  }`}
                                >
                                  {s.name}
                                </button>
                              )
                            })}
                          </div>
                        )}
                        <label className="block">
                          <span className="block text-[11px] font-body text-navy/40 mb-1">
                            {postal.length > 0
                              ? t('trips.postalServicesMore')
                              : t('trips.postalServicesManual')}
                          </span>
                          <input
                            type="text"
                            value={draft[field].postalServices}
                            onChange={(e) =>
                              patchHandover(field, {
                                postalServices: e.target.value,
                              })
                            }
                            placeholder={t('trips.postalServicesPlaceholder') as string}
                            className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
                          />
                        </label>
                      </div>
                    )}

                  {/* Free text, and deliberately so: the market names districts,
                      suburbs and satellite cities, which an airport picker
                      cannot say. */}
                  <label className="block">
                    <span className="block text-[11px] font-body text-navy/40 mb-1">
                      {t('trips.handoverPoints')}
                    </span>
                    <input
                      type="text"
                      value={draft[field].points}
                      onChange={(e) =>
                        patchHandover(field, { points: e.target.value })
                      }
                      placeholder={t('trips.handoverPointsPlaceholder') as string}
                      className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
                    />
                  </label>
                </fieldset>
              ))}
            </div>
          </div>

          <div className="space-y-3 border-t border-navy/10 pt-4">
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('trips.newTripCell.payment')}
            </p>
            {/* The settlement model, not the price, is what this market states:
                61.7 % of posts name one ("без предоплаты" 42.6, "оплата при
                получении" 19.1) and 0.1 % name a sum. So the model is asked
                first and plainly, and the number is marked optional. */}
            <p className="text-[11px] font-body text-navy/40 -mt-1">
              {t('trips.paymentHint')}
            </p>
            <div className="flex flex-wrap gap-2">
              {PAYMENT_MODELS.map((model) => (
                <button
                  key={model}
                  type="button"
                  aria-pressed={draft.paymentModel === model}
                  /* Obligatory since 2026-09-08, so a chip cannot be un-picked:
                     tapping the chosen one again would leave the trip with no
                     answer, and «I changed my mind» here means picking another. */
                  onClick={() => patch({ paymentModel: model })}
                  className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
                    draft.paymentModel === model
                      ? 'border-cyan bg-cyan/10 text-navy'
                      : 'border-navy/20 text-navy/50 hover:border-navy/40'
                  }`}
                >
                  {t(`trips.paymentModel.${model}`)}
                </button>
              ))}
            </div>

            {/* Only asked when it applies. A transfer needs to say through
                what; the other two models do not, and a field that is always
                on screen teaches people to skip the whole block. */}
            {draft.paymentModel === EMONEY_MODEL && (
              <label className="block">
                <span className="block text-[11px] font-body text-navy/40 mb-1">
                  {t('trips.paymentSystems')}
                </span>
                {/* T3.11.07 — the carrier's own shortlist first (owner's
                    decision 2026-09-06). «Наличные при встрече», «Каспи»,
                    «Зелле» are the same three answers on every trip, and the
                    corridor catalogue below cannot know them: it knows what
                    exists in a country, not what this person accepts. Kept
                    once in «Как со мной рассчитаться» and offered here. */}
                {/* Both ends, deduplicated by name: money moves between two
                    countries and the carrier may be paid at either. A method
                    filed under «везде» shows on every route. */}
                {myMethods.length > 0 && (
                  <span className="flex flex-wrap gap-2 mb-2">
                    {myMethods.map((name) => {
                      const current = splitChips(draft.paymentSystems) ?? []
                      const chosen = current.includes(name)
                      return (
                        <button
                          key={name}
                          type="button"
                          aria-pressed={chosen}
                          onClick={() =>
                            patch({
                              paymentSystems: (chosen
                                ? current.filter((x) => x !== name)
                                : [...current, name]
                              ).join(', '),
                            })
                          }
                          className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
                            chosen
                              ? 'border-cyan bg-cyan/10 text-navy'
                              : 'border-cyan/30 text-navy/70 hover:border-cyan'
                          }`}
                        >
                          {name}
                        </button>
                      )
                    })}
                  </span>
                )}
                {/* Then the corridor: arrival country first, then departure —
                    the order the API returns them in. Cash is the first entry
                    of the global set, not a settlement model of its own. */}
                {systems.length > 0 && (
                  <span className="flex flex-wrap gap-2 mb-2">
                    {systems.slice(0, 12).map((s) => {
                      const current = splitChips(draft.paymentSystems) ?? []
                      const chosen = current.includes(s.name)
                      return (
                        <button
                          key={s.code}
                          type="button"
                          aria-pressed={chosen}
                          onClick={() =>
                            patch({
                              paymentSystems: (chosen
                                ? current.filter((x) => x !== s.name)
                                : [...current, s.name]
                              ).join(', '),
                            })
                          }
                          className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
                            chosen
                              ? 'border-cyan bg-cyan/10 text-navy'
                              : 'border-navy/20 text-navy/50 hover:border-navy/40'
                          }`}
                        >
                          {s.name}
                        </button>
                      )
                    })}
                  </span>
                )}
                <input
                  type="text"
                  value={draft.paymentSystems}
                  onChange={(e) => patch({ paymentSystems: e.target.value })}
                  placeholder={t('trips.paymentSystemsPlaceholder') as string}
                  className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan"
                />
                {/* The chips are shown as they are typed, so the comma is
                    visibly doing something rather than being a convention the
                    carrier has to trust. */}
                {splitChips(draft.paymentSystems) && (
                  <span className="flex flex-wrap gap-1 mt-2">
                    {splitChips(draft.paymentSystems)!.map((system) => (
                      <span
                        key={system}
                        className="text-xs font-mono bg-cyan/10 border border-cyan/30 px-2 py-0.5 rounded-full text-navy"
                      >
                        {system}
                      </span>
                    ))}
                  </span>
                )}
              </label>
            )}

            <p className="text-[11px] font-body text-navy/40">
              {t('trips.termsHint')}
            </p>
            <div className="flex flex-wrap gap-3">
              <label className="flex-1 min-w-[6rem]">
                <span className="block text-[11px] font-body text-navy/40 mb-1">
                  {t('trips.pricePerKg')}
                </span>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={draft.pricePerKg}
                  onChange={(e) => patch({ pricePerKg: e.target.value })}
                  className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                />
              </label>
              <label className="flex-1 min-w-[6rem]">
                <span className="block text-[11px] font-body text-navy/40 mb-1">
                  {t('trips.minDealPrice')}
                </span>
                <input
                  type="number"
                  step="any"
                  min="0"
                  value={draft.minDealPrice}
                  onChange={(e) => patch({ minDealPrice: e.target.value })}
                  className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                />
              </label>
              {/* T3.11.07 — the account's currencies, not free text.
                  It was a three-character box, which accepted `RUUB` and every
                  other typo — and a typo in a currency code is a price nobody
                  can compare. The list comes from the profile, in the order set
                  there: the first one is already selected, the rest are one tap
                  away. A currency that is not here is added in the profile,
                  where it stays for every later trip instead of being retyped. */}
              <fieldset className="min-w-[6rem]">
                <legend className="block text-[11px] font-body text-navy/40 mb-1">
                  {t('trips.currency')}
                </legend>
                <div className="flex flex-wrap gap-1.5">
                  {/* Whatever the draft already holds is shown even if it is no
                      longer in the profile list — a trip repeated from an older
                      one, or a currency since removed. Dropping the chip would
                      publish a price in a currency with nothing selected. */}
                  {(prefs.currencies.includes(draft.currency) || !draft.currency
                    ? prefs.currencies
                    : [...prefs.currencies, draft.currency]
                  ).map((code) => {
                    const active = (draft.currency || prefs.currency) === code
                    return (
                      <button
                        key={code}
                        type="button"
                        onClick={() => patch({ currency: code })}
                        aria-pressed={active}
                        className={`px-3 min-h-[2.75rem] rounded-field border text-sm font-mono ${
                          active
                            ? 'border-cyan text-cyan bg-cyan/5'
                            : 'border-navy/20 text-navy/60'
                        }`}
                      >
                        {code}
                      </button>
                    )
                  })}
                </div>
              </fieldset>
            </div>
          </div>
        </>
      )}

      {/* ── Step 4 · services and rules ─────────────────────────────────── */}
      {step === 4 && (
        <>
          <div className="space-y-2">
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('trips.newTripCell.services')}
            </p>
            {/* Every one of these is something this market already sells and
                the platform could not see: onward shipping inside the
                destination country 44.9 %, marketplace pickup 19 %, buying to
                order 18 %, door delivery 8 %, photo reports 1.7 %. */}
            <p className="text-[11px] font-body text-navy/40">
              {t('trips.servicesHint')}
            </p>
            <div className="space-y-2">
              {TRIP_SERVICES.map((service) => {
                const chosen = draft.services.includes(service)
                return (
                  <button
                    key={service}
                    type="button"
                    aria-pressed={chosen}
                    onClick={() =>
                      patch({
                        services: chosen
                          ? draft.services.filter((s) => s !== service)
                          : [...draft.services, service],
                      })
                    }
                    className={`w-full text-left px-3 py-2 min-h-[2.75rem] rounded-field border text-sm font-body flex items-center justify-between gap-2 transition-colors ${
                      chosen
                        ? 'border-cyan bg-cyan/10 text-navy'
                        : 'border-navy/20 text-navy/60 hover:border-navy/40'
                    }`}
                  >
                    {t(`trips.services.${service}`)}
                    {chosen && <span aria-hidden>✓</span>}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="space-y-2 border-t border-navy/10 pt-4">
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('trips.newTripCell.rules')}
            </p>
            <fieldset>
              <legend className="block text-[11px] font-body text-navy/40 mb-1">
                {t('trips.excludedLabel')}
              </legend>
              <div className="flex flex-wrap gap-2">
                {EXCLUSIONS.map((item) => {
                  const chosen = draft.excluded.includes(item)
                  return (
                    <button
                      key={item}
                      type="button"
                      aria-pressed={chosen}
                      onClick={() =>
                        patch({
                          excluded: chosen
                            ? draft.excluded.filter((x) => x !== item)
                            : [...draft.excluded, item],
                        })
                      }
                      className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
                        chosen
                          ? 'border-amber bg-amber/10 text-navy'
                          : 'border-navy/20 text-navy/50 hover:border-navy/40'
                      }`}
                    >
                      {t(`trips.excluded.${item}`)}
                    </button>
                  )
                })}
              </div>
            </fieldset>

            <p className="text-[11px] font-body text-navy/40">
              {t('trips.rulesHint')}
            </p>
            <label htmlFor={rulesId} className="sr-only">
              {t('trips.newTripCell.rules')}
            </label>
            <textarea
              id={rulesId}
              value={draft.carriageRules}
              onChange={(e) => patch({ carriageRules: e.target.value })}
              rows={3}
              maxLength={4000}
              className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
            />
          </div>

          <label className="flex items-start gap-2 text-xs font-body text-navy/60 border-t border-navy/10 pt-4">
            <input
              type="checkbox"
              checked={draft.alsoOnNostr}
              onChange={(e) => patch({ alsoOnNostr: e.target.checked })}
              className="mt-0.5 accent-cyan"
            />
            <span>{t('trips.newTripCell.alsoOnNostr')}</span>
          </label>
        </>
      )}

      {preview}

      {error && (
        <p role="alert" className="text-xs font-mono text-amber text-center">
          {error}
        </p>
      )}

      {/* T3.11.07 — an inline panel, not a second overlay.
          It used to be `fixed inset-0 z-modal`, which was right while the form
          was a page and wrong now that the form is itself a sheet: two stacked
          overlays mean two focus traps, and dismissing the top one by clicking
          the backdrop lands the click on the one underneath. As a panel it also
          stops being dismissible by a stray click, which for a
          restricted-corridor warning is the correct behaviour anyway — it is
          answered, not waved away. */}
      {preflightNotes.length > 0 && (
        <div
          ref={preflightRef}
          role="alertdialog"
          aria-labelledby="preflight-title"
          tabIndex={-1}
          className="border-2 border-amber/50 bg-amber/5 rounded-card p-4 space-y-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber"
        >
          <h3
            id="preflight-title"
            className="font-display font-semibold text-lg text-navy"
          >
            {t('routeNote.preflightTitle', 'Route requires attention')}
          </h3>
          <p className="text-sm font-body text-navy/70">
            {t(
              'routeNote.preflightBody',
              'This corridor has known specifics. Read them below and confirm you understand before publishing.',
            )}
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {preflightNotes.map((n) => (
              <div
                key={n.id}
                className={`border rounded-field p-3 text-xs font-body ${
                  n.status === 'restricted'
                    ? 'bg-danger/5 border-danger/30 text-danger'
                    : 'bg-amber/10 border-amber/40 text-navy'
                }`}
              >
                <p className="font-mono text-xs mb-1">
                  {n.origin_iso}→{n.destination_iso} [{n.status}/{n.severity}]
                </p>
                <p className="font-medium mb-1">{n.headline}</p>
                {n.body && (
                  <p className="text-navy/70 whitespace-pre-line">{n.body}</p>
                )}
              </div>
            ))}
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={() => setPreflightNotes([])}
              className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2 min-h-[2.75rem]"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={() => {
                setPreflightNotes([])
                setAckedPreflight(true)
                handleSubmit()
              }}
              className="bg-navy text-ivory font-display font-medium px-4 py-2 min-h-[2.75rem] rounded-field text-sm hover:bg-navy-mid"
            >
              {t('routeNote.iUnderstand', 'I understand — publish anyway')}
            </button>
          </div>
        </div>
      )}
    </WizardSheet>
  )
}
