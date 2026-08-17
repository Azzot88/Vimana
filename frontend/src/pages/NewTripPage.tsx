import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import { createTrip } from '../api/trips'
import { listRouteNotes, type RouteNote } from '../api/notices'
import AirportSelect from '../components/AirportSelect'
import CategoryBubbles from '../components/CategoryBubbles'
import MonoText from '../components/MonoText'

const DRAFT_KEY = 'trips:draft:v1'

interface Draft {
  origin: string
  destination: string
  departAt: string
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
  origin: '',
  destination: '',
  departAt: '',
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
    return { ...EMPTY, ...parsed, categories: parsed.categories ?? [] }
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
  const navigate = useNavigate()
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)

  const [draft, setDraft] = useState<Draft>(loadDraft)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
  }, [draft])

  // T_UX.11 — the standing rules from the profile are a starting point, not a
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

  const validate = (): string | null => {
    if (!draft.origin || !draft.destination) return t('trips.newTripValidation.route') as string
    if (draft.origin === draft.destination) return t('trips.newTripValidation.sameRoute') as string
    if (!draft.departAt) return t('trips.newTripValidation.date') as string
    const departDate = new Date(draft.departAt)
    if (Number.isNaN(departDate.getTime()) || departDate.getTime() < Date.now()) {
      return t('trips.newTripValidation.pastDate') as string
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
    if (!ackedPreflight) {
      try {
        const { data: notes } = await listRouteNotes({
          origin: draft.origin,
          destination: draft.destination,
        })
        const critical = notes.filter(
          (n) => n.status === 'complex' || n.status === 'restricted',
        )
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
        origin: draft.origin,
        destination: draft.destination,
        depart_at: draft.departAt,
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
        // T_UX.11 — sent explicitly so an emptied field means "this trip has no
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

  const previewDate = draft.departAt
    ? new Date(draft.departAt).toLocaleString(i18n.language, {
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
        {/* Route cell 2x1 */}
        <div className="md:col-span-2 bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.route')}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-[1fr,auto,1fr] gap-3 items-end">
            <div>
              <label className="block text-xs font-body font-medium text-navy/60 mb-1">
                {t('trips.from')}
              </label>
              <AirportSelect
                value={draft.origin}
                onChange={(v) => patch({ origin: v })}
                required
                placeholder="DXB"
              />
            </div>
            <MonoText className="text-2xl text-cyan text-center pb-2 hidden sm:block">
              →
            </MonoText>
            <div>
              <label className="block text-xs font-body font-medium text-navy/60 mb-1">
                {t('trips.to')}
              </label>
              <AirportSelect
                value={draft.destination}
                onChange={(v) => patch({ destination: v })}
                required
                placeholder="JFK"
              />
            </div>
          </div>
        </div>

        {/* Date cell 1x1 */}
        <div className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.date')}
          </p>
          <input
            type="datetime-local"
            value={draft.departAt}
            onChange={(e) => patch({ departAt: e.target.value })}
            required
            className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan"
          />
        </div>

        {/* Terms cell 1x1 — T3.35 */}
        <div className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
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
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.capacity')}
          </p>
          <div className="flex items-baseline gap-2">
            <input
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
            min="0.5"
            max="20"
            step="0.5"
            value={draft.capacity || 0.5}
            onChange={(e) => patch({ capacity: e.target.value })}
            className="w-full accent-cyan"
          />
        </div>

        {/* Categories cell 1x2 (full row) */}
        <div className="md:col-span-2 bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.categories')}
          </p>
          <CategoryBubbles
            selected={draft.categories}
            onChange={(next) => patch({ categories: next })}
          />
        </div>

        {/* Carriage rules cell 1x2 — T_UX.11 */}
        <div className="md:col-span-2 bg-white rounded-card border border-navy/10 p-4 space-y-2">
          <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
            {t('trips.newTripCell.rules')}
          </p>
          <p className="text-[11px] font-body text-navy/40">{t('trips.rulesHint')}</p>
          <textarea
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
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <MonoText className="text-lg text-navy font-medium">
                {draft.origin || '???'} → {draft.destination || '???'}
              </MonoText>
              <MonoText className="text-sm text-navy/60">{previewDate}</MonoText>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-body text-navy/50">
              <span>
                {t('trips.capacity')}:{' '}
                <MonoText className="text-xs">{draft.capacity || '?'} {t('trips.kg')}</MonoText>
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
