import { useId, useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { createTrip } from '../api/trips'
import { listRouteNotes, type RouteNote } from '../api/notices'
import AirportSelect from '../components/AirportSelect'
import CategoryBubbles from '../components/CategoryBubbles'
import MonoText from '../components/MonoText'
import { usePrefs } from '../hooks/usePrefs'

// T3.11.07 — bumped from v1 when the route became a chain. A draft saved under
// the old shape carries a flat origin/destination/date and cannot be read as
// legs; a stale one is a lost half-filled form, a misread one is a form that
// looks filled and is not.
const DRAFT_KEY = 'trips:draft:v2'

/** T3.11.15 — one flight. Strings throughout: these come from inputs, and an
 *  empty string is a real answer ("not stated yet") that a number is not. */
interface LegDraft {
  origin: string
  destination: string
  departAt: string
  flownBy: 'self' | 'proxy'
}

const EMPTY_LEG: LegDraft = {
  origin: '',
  destination: '',
  departAt: '',
  flownBy: 'self',
}

// Matches `core.trip_legs.MAX_LEGS` on the server. Real posts top out at six
// cities; the limit exists so one listing cannot become a database.
const MAX_LEGS = 10

interface Draft {
  legs: LegDraft[]
  capacity: string
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
  capacity: '',
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
    }
  } catch {
    return EMPTY
  }
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
      // The next flight starts where the last one landed far more often than
      // not — «Москва — Майами — Лос-Анджелес», «Дубай — Москва — Дубай». It
      // stays editable, so guessing costs a keystroke and saves several.
      return {
        ...prev,
        legs: [...prev.legs, { ...EMPTY_LEG, origin: last?.destination ?? '' }],
      }
    })
  }, [])

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
    const cap = parseFloat(draft.capacity)
    if (!cap || cap < 0.5) return t('trips.newTripValidation.capacity') as string
    return null
  }

  const [preflightNotes, setPreflightNotes] = useState<RouteNote[]>([])
  const [ackedPreflight, setAckedPreflight] = useState(false)

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setError('')
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }
    const cap = parseFloat(draft.capacity)
    if (cap > 15 && !window.confirm(t('trips.newTripValidation.capacityWarning') as string)) {
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
          flown_by: leg.flownBy,
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

  const formatDeparture = (value: string) =>
    value
      ? new Date(value).toLocaleString(i18n.language, {
          dateStyle: 'medium',
          timeStyle: 'short',
        })
      : '—'

  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-display font-bold text-2xl text-navy">
          {t('trips.newTrip')}
        </h1>
        <div className="flex gap-2">
          {showHookIcon('🎤', t('trips.newTripHook.voice'), VOICE_ENABLED)}
          {showHookIcon('📷', t('trips.newTripHook.scan'), SCAN_ENABLED)}
          <button
            type="button"
            aria-label={t('trips.newTripHook.manual') as string}
            className="w-10 h-10 rounded-field border border-navy/40 bg-navy text-ivory"
            title={t('trips.newTripHook.manual') as string}
          >
            <span aria-hidden="true" className="text-lg">
              ⌨️
            </span>
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Route cell — the whole chain, T3.11.07 */}
        <div className="md:col-span-3 bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
              {t('trips.newTripCell.route')}
            </p>
            <MonoText className="text-[11px] text-navy/40">
              {draft.legs.length}/{MAX_LEGS}
            </MonoText>
          </div>
          {/* DESIGNGUIDELINES §9b — what this field changes and where it shows. */}
          <p className="text-[11px] font-body text-navy/40 -mt-1">
            {t('trips.routeHint')}
          </p>

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

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 items-end">
                <div>
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
                <fieldset>
                  <legend className="block text-xs font-body font-medium text-navy/60 mb-1">
                    {t('trips.flownBy.label')}
                  </legend>
                  {/* Asked outright rather than assumed. "Flying in person" is
                      the most valuable claim on this market, and it appears in
                      the same posts as "(a friend is flying)" — so the platform
                      does not let it be implied by silence. */}
                  <div className="flex gap-2">
                    {(['self', 'proxy'] as const).map((who) => (
                      <label
                        key={who}
                        className={`flex-1 text-center text-xs font-body px-3 py-2 min-h-[2.75rem] flex items-center justify-center rounded-field border cursor-pointer transition-colors ${
                          leg.flownBy === who
                            ? 'border-cyan bg-cyan/10 text-navy'
                            : 'border-navy/20 text-navy/50 hover:border-navy/40'
                        }`}
                      >
                        <input
                          type="radio"
                          name={`${departId}-flownBy-${index}`}
                          value={who}
                          checked={leg.flownBy === who}
                          onChange={() => patchLeg(index, { flownBy: who })}
                          className="sr-only"
                        />
                        {t(`trips.flownBy.${who}`)}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>

              {draft.legs.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeLeg(index)}
                  className="text-xs font-body text-navy/40 hover:text-danger transition-colors"
                >
                  {t('trips.removeLeg')}
                </button>
              )}
            </fieldset>
          ))}

          {draft.legs.length < MAX_LEGS && (
            <button
              type="button"
              onClick={addLeg}
              className="w-full border border-dashed border-navy/25 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy/60 hover:border-cyan hover:text-navy transition-colors"
            >
              {t('trips.addLeg')}
            </button>
          )}
        </div>

        {/* Terms cell 2x1 — T3.35. Widened in T3.11.07 so the Bento rows close:
            route 3 · terms 2 + capacity 1 · categories 3 · rules 2 + publish 1 ·
            preview 3. The date cell that used to sit beside the route moved
            inside each leg, and without this the grid left holes. */}
        <div className="md:col-span-2 bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.terms')}
          </p>
          <p className="text-[11px] font-body text-navy/40 -mt-1">
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
                onChange={(e) =>
                  patch({ currency: e.target.value.toUpperCase() })
                }
                className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
              />
            </label>
          </div>
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
        </div>

        {/* Capacity cell 1x1 */}
        <div className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <label
            id={capacityLabelId}
            htmlFor={capacityId}
            className="block text-xs font-display font-semibold text-navy/50 uppercase tracking-wide"
          >
            {t('trips.newTripCell.capacity')}
          </label>
          <div className="flex items-baseline gap-2">
            <input
              id={capacityId}
              type="number"
              step="0.5"
              min="0.5"
              max="20"
              value={draft.capacity}
              onChange={(e) => patch({ capacity: e.target.value })}
              required
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
        </div>

        {/* Categories cell — full row */}
        <div className="md:col-span-3 bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.categories')}
          </p>
          <CategoryBubbles
            selected={draft.categories}
            onChange={(next) => patch({ categories: next })}
          />
        </div>

        {/* Carriage rules cell 1x2 — T_UX.15 */}
        <div className="md:col-span-2 bg-white rounded-card border border-navy/10 p-4 space-y-2">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.rules')}
          </p>
          <p className="text-[11px] font-body text-navy/40">{t('trips.rulesHint')}</p>
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

        {/* Publish cell 1x1 */}
        <div className="bg-white rounded-card border border-navy/10 p-4 space-y-3 flex flex-col">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.publish')}
          </p>
          <label className="flex items-start gap-2 text-xs font-body text-navy/60">
            <input
              type="checkbox"
              checked={draft.alsoOnNostr}
              onChange={(e) => patch({ alsoOnNostr: e.target.checked })}
              className="mt-0.5 accent-cyan"
            />
            <span>{t('trips.newTripCell.alsoOnNostr')}</span>
          </label>
          <button
            type="submit"
            disabled={loading}
            className="mt-auto bg-amber text-white font-display font-semibold px-4 py-3 min-h-[2.75rem] rounded-field text-sm hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {loading ? t('common.loading') : t('trips.publish')}
          </button>
          <p className="text-[10px] font-mono text-navy/30 text-center">
            ⌘/Ctrl + ⏎
          </p>
        </div>

        {/* Preview cell 2x1 — sticky bottom on desktop */}
        <div className="md:col-span-3 bg-gradient-to-br from-navy/5 to-cyan/5 rounded-card border border-navy/10 p-4">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide mb-2">
            {t('trips.newTripCell.preview')}
          </p>
          <div className="bg-white rounded-card border border-navy/10 p-4">
            {/* One row per flight. Carriers are used to seeing their whole post
                before it goes out, and a chain summarised as first→last would
                hide the very segment they added the chain for. */}
            <div className="space-y-1">
              {draft.legs.map((leg, index) => (
                <div
                  key={index}
                  className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-2"
                >
                  <MonoText className="text-lg text-navy font-medium">
                    {leg.origin || '???'} → {leg.destination || '???'}
                    {leg.flownBy === 'proxy' && (
                      <span className="ml-2 text-xs font-body text-navy/50">
                        {t('trips.flownBy.proxyChip')}
                      </span>
                    )}
                  </MonoText>
                  <MonoText className="text-sm text-navy/60">
                    {formatDeparture(leg.departAt)}
                  </MonoText>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
              <span>
                {t('trips.capacity')}:{' '}
                <MonoText className="text-xs">{draft.capacity ? prefs.weight(Number(draft.capacity)) : '?'}</MonoText>
              </span>
              {draft.categories.length > 0 && (
                <span className="flex flex-wrap gap-1">
                  {draft.categories.map((c) => (
                    <span
                      key={c}
                      className="text-xs font-mono bg-ivory px-2 py-0.5 rounded text-navy/60"
                    >
                      {c}
                    </span>
                  ))}
                </span>
              )}
            </div>
          </div>
        </div>
      </form>

      {error && (
        <p className="text-xs font-mono text-amber text-center">{error}</p>
      )}

      <div className="text-center">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="text-sm font-body text-navy/50 hover:text-navy transition-colors"
        >
          {t('common.cancel')}
        </button>
      </div>

      {preflightNotes.length > 0 && (
        <div
          className="fixed inset-0 bg-navy/60 backdrop-blur-sm z-modal flex items-center justify-center p-4"
          onClick={() => setPreflightNotes([])}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-card p-6 max-w-lg w-full space-y-4 shadow-2xl"
          >
            <h3 className="font-display font-semibold text-lg text-navy">
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
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setPreflightNotes([])}
                className="text-sm font-body text-navy/60 hover:text-navy px-3 py-2"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={() => {
                  setPreflightNotes([])
                  setAckedPreflight(true)
                  handleSubmit()
                }}
                className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-field text-sm hover:bg-navy-mid"
              >
                {t('routeNote.iUnderstand', 'I understand — publish anyway')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
