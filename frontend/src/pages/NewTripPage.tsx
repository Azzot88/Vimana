import { useId, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import {
  createTrip,
  EXCLUSIONS,
  PAYMENT_MODELS,
  TRIP_SERVICES,
  type Exclusion,
  type PaymentModel,
  type TripService,
} from '../api/trips'
import { listRouteNotes, type RouteNote } from '../api/notices'
import AirportSelect from '../components/AirportSelect'
import CategoryBubbles from '../components/CategoryBubbles'
import MonoText from '../components/MonoText'
import WizardSheet from '../components/WizardSheet'
import { usePrefs } from '../hooks/usePrefs'

/** T3.11.20 — four steps, and only the first is required.
 *
 *  The order is the order of certainty. Step 1 is what the carrier knows by
 *  heart and can answer in fifteen seconds; step 4 is commercial decisions that
 *  need thinking about. Putting money earlier is the classic way to lose the
 *  people who would have published.
 */
const TOTAL_STEPS = 4

// T3.11.07 — bumped from v1 when the route became a chain, and again when "who
// is flying" moved from the leg to the trip. Both times for the same reason: a
// draft read under the wrong shape looks filled and is not. Here a v2 draft
// would carry the answer on each leg, where nothing reads it any more, and
// publish `self` for a carrier who had said otherwise.
const DRAFT_KEY = 'trips:draft:v3'

/** T3.11.15 — one flight. Strings throughout: these come from inputs, and an
 *  empty string is a real answer ("not stated yet") that a number is not.
 *
 *  Note what is *not* here: who is flying. The model keeps `flown_by` per leg,
 *  because a chain can genuinely be flown by two people, but the form asks it
 *  once for the whole trip (owner's decision 2026-09-06) — the answer is almost
 *  always the same for every leg, and asking it three times makes a real
 *  question look like a formality. */
interface LegDraft {
  origin: string
  destination: string
  departAt: string
}

const EMPTY_LEG: LegDraft = {
  origin: '',
  destination: '',
  departAt: '',
}

/** A leg the carrier has finished answering. Used to decide when the next one
 *  may be offered: a form that hands out empty rows before the first is filled
 *  shows work instead of asking for it. */
const isLegComplete = (leg: LegDraft) =>
  Boolean(leg.origin && leg.destination && leg.departAt)

// Matches `core.trip_legs.MAX_LEGS` on the server. Real posts top out at six
// cities; the limit exists so one listing cannot become a database.
const MAX_LEGS = 10

/** T3.11.07 — one end of the handover. `points` is one text field rather than a
 *  repeater: carriers write "Tustin, Irvine or LAX" in one breath, and three
 *  boxes to fill would be three boxes left empty. Split on commas on submit. */
interface HandoverDraft {
  methods: string[]
  points: string
}

const EMPTY_HANDOVER: HandoverDraft = { methods: [], points: '' }

// Matches `schemas.marketplace.HANDOVER_METHODS` and reuses the card labels
// (`cards.opt.*`): one vocabulary, named once, so a carrier cannot advertise a
// method no deal card can ever name.
const HANDOVER_METHODS = [
  'in_person',
  'local_post',
  'courier',
  'parcel_locker',
  'poste_restante',
] as const

const SPACE_KINDS = ['cabin', 'checked_partial', 'checked_full'] as const
const SIZE_HINTS = ['small', 'medium', 'large'] as const

interface Draft {
  legs: LegDraft[]
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
  // T3.11.15 — the customs half. The ceiling and whether it is spent are two
  // separate facts: "the luxury allowance is used up" appears in posts that
  // still take documents on the same flight.
  declaredValueStatus: 'open' | 'exhausted'
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
  categories: string[]
  alsoOnNostr: boolean
  // T3.35 — the carrier's baseline terms. Strings because they come from
  // inputs; empty means "not stated", which is a real answer.
  pricePerKg: string
  minDealPrice: string
  currency: string
  maxDeclaredValue: string
  carriageRules: string
}

const EMPTY: Draft = {
  legs: [{ ...EMPTY_LEG }],
  flownBy: 'self',
  capacity: '',
  spaceKind: 'unspecified',
  sizeHint: '',
  declaredValueStatus: 'open',
  handoverOrigin: { ...EMPTY_HANDOVER },
  handoverDestination: { ...EMPTY_HANDOVER },
  excluded: [],
  services: [],
  paymentModel: '',
  categories: [],
  alsoOnNostr: true,
  pricePerKg: '',
  minDealPrice: '',
  currency: 'USD',
  maxDeclaredValue: '',
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
      // A saved draft with an empty chain would render a route cell with no
      // rows and no way to add one.
      legs: parsed.legs?.length ? parsed.legs : [{ ...EMPTY_LEG }],
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
function toHandover(side: HandoverDraft) {
  const points = side.points
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean)
    // The API caps this at six; trimming here means a carrier who typed seven
    // gets a published trip rather than a validation error about a field they
    // filled in generously.
    .slice(0, 6)
  if (side.methods.length === 0 && points.length === 0) return null
  return { methods: side.methods, points }
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
  const originId = useId()
  const destId = useId()
  const departId = useId()
  const capacityId = useId()
  // T_TEST.8 — the slider is a second way into the same number, so it carries
  // the same name rather than a made-up one of its own. Hiding it from screen
  // readers was the other option and it is worse: dragging is the easier input
  // for some motor impairments, and the field it duplicates stays reachable.
  const capacityLabelId = useId()
  const rulesId = useId()
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)

  const [draft, setDraft] = useState<Draft>(loadDraft)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [askingToClose, setAskingToClose] = useState(false)

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
  const goToStep = useCallback(
    (next: number, replace = false) => {
      setParams({ step: String(next) }, { replace })
    },
    [setParams],
  )

  useEffect(() => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
  }, [draft])

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

  // T3.11.07 — the chain is edited by index; the three helpers exist so no
  // caller has to copy the array by hand and get the splice wrong.
  const patchLeg = useCallback((index: number, delta: Partial<LegDraft>) => {
    setDraft((prev) => ({
      ...prev,
      legs: prev.legs.map((leg, i) => (i === index ? { ...leg, ...delta } : leg)),
    }))
  }, [])

  const addLeg = useCallback(() => {
    setDraft((prev) => {
      if (prev.legs.length >= MAX_LEGS) return prev
      const last = prev.legs[prev.legs.length - 1]
      // Guarded here as well as in the button's `disabled`: a disabled control
      // is a hint, not a rule, and this one is also reachable by keyboard.
      if (last && !isLegComplete(last)) return prev
      // The next flight starts where the last one landed far more often than
      // not — «Москва — Майами — Лос-Анджелес», «Дубай — Москва — Дубай». It
      // stays editable, so guessing costs a keystroke and saves several.
      return {
        ...prev,
        legs: [...prev.legs, { ...EMPTY_LEG, origin: last?.destination ?? '' }],
      }
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

  const removeLeg = useCallback((index: number) => {
    setDraft((prev) =>
      prev.legs.length <= 1
        ? prev
        : { ...prev, legs: prev.legs.filter((_, i) => i !== index) },
    )
  }, [])

  const validate = (): string | null => {
    for (const [index, leg] of draft.legs.entries()) {
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
      const previous = draft.legs[index - 1]
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
      if (Number.isNaN(cap) || cap < 0.5) {
        return t('trips.newTripValidation.capacity') as string
      }
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
    const untouched =
      draft.legs.length === 1 &&
      !draft.legs[0].origin &&
      !draft.legs[0].destination &&
      !draft.legs[0].departAt
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
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }
    const cap = draft.capacity ? parseFloat(draft.capacity) : null
    if (
      cap !== null &&
      cap > 15 &&
      !window.confirm(t('trips.newTripValidation.capacityWarning') as string)
    ) {
      return
    }
    // T_UX.2 pt.3 — pre-flight warning for complex/restricted corridors.
    // T3.11.07 — asked for **every** leg, not just the endpoints. A chain
    // through Istanbul is subject to Turkish transit rules, and PRD §3.11.1 is
    // explicit that the transit node is present in the main corridor always
    // rather than occasionally: checking only first-to-last would skip the leg
    // most likely to carry a restriction.
    if (!ackedPreflight) {
      try {
        const perLeg = await Promise.all(
          draft.legs.map((leg) =>
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
      await createTrip({
        // T3.11.07 — the route travels as the chain the carrier typed. Order is
        // the array order; the server assigns it and derives the trip's
        // origin, destination and date from the first and last leg.
        legs: draft.legs.map((leg) => ({
          origin: leg.origin,
          destination: leg.destination,
          depart_at: leg.departAt,
          // One answer for the trip, written onto every leg. The model keeps it
          // per leg so a chain flown by two people stays expressible later.
          flown_by: draft.flownBy,
        })),
        capacity: cap,
        allowed_categories: draft.categories,
        // Empty stays empty: a trip without a stated price is "price on
        // request", not a trip priced at zero.
        price_per_kg: draft.pricePerKg ? Number(draft.pricePerKg) : null,
        min_deal_price: draft.minDealPrice ? Number(draft.minDealPrice) : null,
        currency: draft.currency || 'USD',
        max_declared_value: draft.maxDeclaredValue
          ? Number(draft.maxDeclaredValue)
          : null,
        // T3.11.07 — the two capacities and the two ends of the handover.
        // `sizeHint` empty stays null: "did not say" and "small" are different
        // answers and the API keeps them apart.
        declared_value_status: draft.declaredValueStatus,
        space_kind: draft.spaceKind,
        size_hint: draft.sizeHint || null,
        handover_origin: toHandover(draft.handoverOrigin),
        handover_destination: toHandover(draft.handoverDestination),
        // Nothing ticked is `null`, not `[]`: "said nothing" and "considered it
        // and excludes nothing" are different answers, and the card reads them
        // differently.
        excluded: draft.excluded.length > 0 ? draft.excluded : null,
        services: draft.services.length > 0 ? draft.services : null,
        payment_model: draft.paymentModel || null,
        // T_UX.15 — sent explicitly so an emptied field means "this trip has no
        // rules" rather than "fall back to my template".
        carriage_rules: draft.carriageRules,
      })
      localStorage.removeItem(DRAFT_KEY)
      navigate('/trips')
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
  const firstOrigin = draft.legs[0]?.origin ?? ''
  const lastDestination = draft.legs[draft.legs.length - 1]?.destination ?? ''

  const formatDeparture = (value: string) =>
    value
      ? new Date(value).toLocaleString(i18n.language, {
          dateStyle: 'medium',
          timeStyle: 'short',
        })
      : '—'


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
          {draft.legs.map((leg, index) => (
            <div
              key={index}
              className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-2"
            >
              <MonoText className="text-lg text-navy font-medium">
                {leg.origin || '???'} → {leg.destination || '???'}
              </MonoText>
              <MonoText className="text-sm text-navy/60">
                {formatDeparture(leg.departAt)}
              </MonoText>
            </div>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
          {draft.capacity && (
            <span>
              {t('trips.capacity')}:{' '}
              <MonoText className="text-xs">
                {prefs.weight(Number(draft.capacity))}
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
          {draft.declaredValueStatus === 'exhausted' && (
            <span className="text-amber">
              {t('trips.declaredValueStatus.exhausted')}
            </span>
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
      {loading ? t('common.loading') : t('trips.publish')}
    </button>
  )

  return (
    <WizardSheet
      step={step}
      total={TOTAL_STEPS}
      title={stepTitles[step - 1] as string}
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

          {draft.legs.map((leg, index) => (
            <fieldset
              key={index}
              className="border border-navy/10 rounded-field p-3 space-y-3"
            >
              <legend className="px-1 text-[11px] font-mono text-navy/40">
                {t('trips.legNumber', { n: index + 1 })}
              </legend>
              <div className="grid grid-cols-1 sm:grid-cols-[1fr,auto,1fr] gap-3 items-end">
                <div>
                  <label
                    htmlFor={`${originId}-${index}`}
                    className="block text-xs font-body font-medium text-navy/60 mb-1"
                  >
                    {t('trips.from')}
                  </label>
                  <AirportSelect
                    inputId={`${originId}-${index}`}
                    value={leg.origin}
                    onChange={(v) => patchLeg(index, { origin: v })}
                    required
                    placeholder="DXB"
                  />
                </div>
                <MonoText className="text-2xl text-cyan text-center pb-2 hidden sm:block">
                  →
                </MonoText>
                <div>
                  <label
                    htmlFor={`${destId}-${index}`}
                    className="block text-xs font-body font-medium text-navy/60 mb-1"
                  >
                    {t('trips.to')}
                  </label>
                  <AirportSelect
                    inputId={`${destId}-${index}`}
                    value={leg.destination}
                    onChange={(v) => patchLeg(index, { destination: v })}
                    required
                    placeholder="JFK"
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-end justify-between gap-3">
                <div className="min-w-[12rem] flex-1">
                  <label
                    htmlFor={`${departId}-${index}`}
                    className="block text-xs font-body font-medium text-navy/60 mb-1"
                  >
                    {t('trips.newTripCell.date')}
                  </label>
                  {/* Time is part of the answer, not a tail on the date: 29.8 %
                      of real posts state the hour, and the handover window is
                      counted back from it. */}
                  <input
                    id={`${departId}-${index}`}
                    type="datetime-local"
                    value={leg.departAt}
                    onChange={(e) => patchLeg(index, { departAt: e.target.value })}
                    required
                    className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                  />
                </div>

                {draft.legs.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeLeg(index)}
                    className="text-xs font-body text-navy/40 hover:text-danger transition-colors py-2 min-h-[2.75rem]"
                  >
                    {t('trips.removeLeg')}
                  </button>
                )}
              </div>
            </fieldset>
          ))}

          {/* The next flight is offered only once this one is answered: handing
              out empty rows in advance shows work nobody asked for. */}
          {draft.legs.length < MAX_LEGS && (
            <button
              type="button"
              onClick={addLeg}
              disabled={!isLegComplete(draft.legs[draft.legs.length - 1])}
              title={
                isLegComplete(draft.legs[draft.legs.length - 1])
                  ? undefined
                  : (t('trips.addLegBlocked') as string)
              }
              className="w-full border border-dashed border-navy/25 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy/60 hover:border-cyan hover:text-navy transition-colors disabled:opacity-40 disabled:hover:border-navy/25 disabled:hover:text-navy/60 disabled:cursor-not-allowed"
            >
              {t('trips.addLeg')}
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
            <div className="flex items-baseline gap-2">
              <input
                id={capacityId}
                type="number"
                step="0.5"
                min="0.5"
                max="20"
                value={draft.capacity}
                onChange={(e) => patch({ capacity: e.target.value })}
                placeholder="5"
                className="w-24 border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-lg font-mono text-navy focus:outline-none focus:border-cyan"
              />
              <MonoText className="text-sm text-navy/60">kg</MonoText>
            </div>
            <input
              type="range"
              aria-labelledby={capacityLabelId}
              min="0.5"
              max="20"
              step="0.5"
              value={draft.capacity || 0.5}
              onChange={(e) => patch({ capacity: e.target.value })}
              className="w-full accent-cyan"
            />
            {/* The second way to answer the same question. Kilograms are named
                in 2.4 % of real posts and "small / not big" in 9.9 %. */}
            <fieldset>
              <legend className="block text-[11px] font-body text-navy/40 mb-1">
                {t('trips.sizeHint.label')}
              </legend>
              <div className="flex flex-wrap gap-2">
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
              </div>
            </fieldset>
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
            <label className="block">
              <span className="block text-[11px] font-body text-navy/40 mb-1">
                {t('trips.maxDeclaredValue')}
              </span>
              <input
                type="number"
                step="any"
                min="0"
                value={draft.maxDeclaredValue}
                onChange={(e) => patch({ maxDeclaredValue: e.target.value })}
                className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
              />
            </label>
            <fieldset>
              <legend className="block text-[11px] font-body text-navy/40 mb-1">
                {t('trips.declaredValueStatus.label')}
              </legend>
              <div className="flex gap-2">
                {(['open', 'exhausted'] as const).map((state) => (
                  <label
                    key={state}
                    className={`flex-1 text-center text-xs font-body px-3 py-2 min-h-[2.75rem] flex items-center justify-center rounded-field border cursor-pointer transition-colors ${
                      draft.declaredValueStatus === state
                        ? state === 'exhausted'
                          ? 'border-amber bg-amber/10 text-navy'
                          : 'border-cyan bg-cyan/10 text-navy'
                        : 'border-navy/20 text-navy/50 hover:border-navy/40'
                    }`}
                  >
                    <input
                      type="radio"
                      name="declaredValueStatus"
                      value={state}
                      checked={draft.declaredValueStatus === state}
                      onChange={() => patch({ declaredValueStatus: state })}
                      className="sr-only"
                    />
                    {t(`trips.declaredValueStatus.${state}`)}
                  </label>
                ))}
              </div>
            </fieldset>
            {draft.declaredValueStatus === 'exhausted' && (
              <p className="text-[11px] font-body text-navy/50">
                {t('trips.declaredValueStatus.exhaustedNote')}
              </p>
            )}
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
                  ['handoverOrigin', firstOrigin] as const,
                  ['handoverDestination', lastDestination] as const,
                ]
              ).map(([field, place]) => (
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
                          onClick={() =>
                            patchHandover(field, {
                              methods: chosen
                                ? draft[field].methods.filter((m) => m !== method)
                                : [...draft[field].methods, method],
                            })
                          }
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
                  onClick={() =>
                    patch({
                      paymentModel: draft.paymentModel === model ? '' : model,
                    })
                  }
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
              <label className="w-24">
                <span className="block text-[11px] font-body text-navy/40 mb-1">
                  {t('trips.currency')}
                </span>
                <input
                  maxLength={3}
                  value={draft.currency}
                  onChange={(e) => patch({ currency: e.target.value.toUpperCase() })}
                  className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
                />
              </label>
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
