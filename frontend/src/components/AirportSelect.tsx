import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import {
  airportsInCity,
  listCitiesInCountry,
  listCountries,
  lookupAirports,
  nearestAirports,
  popularAirports,
  type Airport,
  type CityMatch,
  type CountryCount,
} from '../api/airports'

/** T3.11.07 — the airports this viewer has actually chosen before.
 *
 *  An empty field with a blinking cursor asks the carrier to recall an IATA
 *  code from memory. The strongest answer is their own history: people fly the
 *  same corridor repeatedly — 5.4 % of real posts say "I fly every week" in as
 *  many words — so the code they picked last time is very often the one they
 *  want now.
 *
 *  Local to the browser on purpose: it is a convenience, it is per-device, and
 *  it is nobody's business but the viewer's. Wrapped in try/catch because
 *  storage throws outright in a private window with site data blocked.
 */
const RECENT_KEY = 'airports:recent:v1'
const RECENT_MAX = 6

function loadRecent(): Airport[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    return raw ? (JSON.parse(raw) as Airport[]) : []
  } catch {
    return []
  }
}

function rememberAirport(a: Airport) {
  try {
    const next = [a, ...loadRecent().filter((x) => x.iata !== a.iata)].slice(0, RECENT_MAX)
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    /* a picker that throws because history could not be saved is worse than
       a picker with no history. */
  }
}

interface Props {
  value: string
  onChange: (iata: string) => void
  placeholder?: string
  required?: boolean
  /** T_TEST.8 — the caller owns the visible label, so it has to own the id the
   *  label points at. Without this the control is a text field with no name. */
  inputId?: string
}

function isoToFlag(iso: string): string {
  if (!iso || iso.length !== 2) return ''
  return iso.toUpperCase().replace(/./g, (c) => String.fromCodePoint(127397 + c.charCodeAt(0)))
}

interface CountryRow {
  iso: string
  name: string
  nameEn: string
  count: number
}

export default function AirportSelect({ value, onChange, placeholder, required, inputId }: Props) {
  const { t, i18n } = useTranslation()
  const [query, setQuery] = useState(value)
  const [countries, setCountries] = useState<CountryCount[]>([])
  const [countryFilter, setCountryFilter] = useState<{ iso: string; name: string } | null>(null)
  const [cityFilter, setCityFilter] = useState<{ iso: string; city: string } | null>(null)
  const [subtitle, setSubtitle] = useState<{ iso: string; countryName: string; city: string } | null>(null)
  const [countryMatches, setCountryMatches] = useState<CountryRow[]>([])
  const [cityMatches, setCityMatches] = useState<CityMatch[]>([])
  const [airportMatches, setAirportMatches] = useState<Airport[]>([])
  const [open, setOpen] = useState(false)
  const [geoLoading, setGeoLoading] = useState(false)
  // T3.11.07 — the three answers to an empty field, in order of how much they
  // know about this particular person: their own history, then this platform's
  // traffic, then where they are standing.
  const [recent, setRecent] = useState<Airport[]>([])
  const [popular, setPopular] = useState<Airport[]>([])
  const [nearby, setNearby] = useState<Airport[]>([])
  const wrapperRef = useRef<HTMLDivElement>(null)
  // T3.11.07 — the list is drawn in a portal on `document.body`, not inside the
  // field. Absolutely positioned it was clipped by the first ancestor that
  // scrolls, and the wizard's step is exactly that: a sheet with
  // `overflow-y: auto`. So the panel is measured against the field and placed
  // in fixed coordinates, which no ancestor can crop.
  const panelRef = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<{
    top: number
    left: number
    width: number
    openUp: boolean
  } | null>(null)

  const displayNames = useMemo(
    () => new Intl.DisplayNames([i18n.language], { type: 'region' }),
    [i18n.language],
  )
  const enDisplayNames = useMemo(
    () => new Intl.DisplayNames(['en'], { type: 'region' }),
    [],
  )

  const countryRows: CountryRow[] = useMemo(() => {
    return countries.map((c) => ({
      iso: c.iso,
      name: displayNames.of(c.iso) ?? c.iso,
      nameEn: enDisplayNames.of(c.iso) ?? c.iso,
      count: c.count,
    }))
  }, [countries, displayNames, enDisplayNames])

  useEffect(() => {
    listCountries().then((r) => setCountries(r.data)).catch(() => {})
  }, [])

  // T3.11.07 — the suggestions are gathered once per mount, not per focus: they
  // do not change between two focuses of the same field, and a request on every
  // focus would fire several times while somebody tabs through a chain of legs.
  useEffect(() => {
    setRecent(loadRecent())
    popularAirports(6)
      .then((r) => setPopular(r.data))
      .catch(() => {})

    // Location is asked for **only if the viewer has already granted it**.
    // Prompting on focus would put a browser permission dialog in front of
    // somebody who came to type three letters, which is how a picker teaches
    // people to say no. The explicit button below stays the way to grant it.
    if (!navigator.geolocation || !navigator.permissions?.query) return
    let cancelled = false
    navigator.permissions
      .query({ name: 'geolocation' as PermissionName })
      .then((status) => {
        if (cancelled || status.state !== 'granted') return
        navigator.geolocation.getCurrentPosition(
          async (pos) => {
            try {
              const { data } = await nearestAirports(
                pos.coords.latitude,
                pos.coords.longitude,
                4,
              )
              if (!cancelled) setNearby(data)
            } catch {
              /* silent — a suggestion that fails to load is not an error the
                 viewer can act on. */
            }
          },
          () => {},
          { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
        )
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setQuery(value)
  }, [value])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const target = e.target as Node
      // The panel lives outside this subtree now, so it has to be checked
      // separately: closing on `mousedown` would unmount the option before its
      // `click` ever lands, and the pick would silently do nothing.
      if (wrapperRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const measure = useCallback(() => {
    const el = wrapperRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const below = window.innerHeight - r.bottom
    // Flip up only when there is genuinely less room below than above: on a
    // phone with the keyboard open the field often sits in the top third, and
    // a list that always drops down would open under the keyboard.
    const openUp = below < 260 && r.top > below
    setAnchor({
      top: openUp ? r.top : r.bottom,
      left: r.left,
      width: r.width,
      openUp,
    })
  }, [])

  useEffect(() => {
    if (!open) return
    measure()
    window.addEventListener('resize', measure)
    // Capture phase: the field may scroll inside a sheet rather than the page,
    // and a scroll event on that container does not bubble to `window`.
    window.addEventListener('scroll', measure, true)
    return () => {
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [open, measure])

  useEffect(() => {
    const q = query.trim()
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        if (cityFilter) {
          const { data } = await airportsInCity(cityFilter.iso, cityFilter.city)
          if (cancelled) return
          const filtered = q
            ? data.filter((a) => a.iata.toLowerCase().includes(q.toLowerCase()))
            : data
          setCountryMatches([])
          setCityMatches([])
          setAirportMatches(filtered.length > 0 ? filtered : data)
          return
        }
        if (countryFilter) {
          const { data: cities } = await listCitiesInCountry(countryFilter.iso)
          if (cancelled) return
          const qLow = q.toLowerCase()
          const filtered = q
            ? cities.filter((c) => c.city.toLowerCase().includes(qLow))
            : cities
          setCountryMatches([])
          setCityMatches(
            filtered.slice(0, 12).map((c) => ({ iso: countryFilter.iso, city: c.city, count: c.count })),
          )
          setAirportMatches([])
          return
        }
        if (!q) {
          setCountryMatches([])
          setCityMatches([])
          setAirportMatches([])
          return
        }
        const qLow = q.toLowerCase()
        const countryHits = countryRows
          .filter(
            (c) =>
              c.name.toLowerCase().includes(qLow) ||
              c.nameEn.toLowerCase().includes(qLow) ||
              c.iso.toLowerCase() === qLow,
          )
          .slice(0, 5)
        const { data } = await lookupAirports(q)
        if (cancelled) return
        setCountryMatches(countryHits)
        setCityMatches(data.cities)
        setAirportMatches(data.airports)
      } catch {
        if (!cancelled) {
          setCountryMatches([])
          setCityMatches([])
          setAirportMatches([])
        }
      }
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, countryFilter, cityFilter, countryRows])

  const handleGeolocation = () => {
    if (!navigator.geolocation) return
    setGeoLoading(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const { data } = await nearestAirports(pos.coords.latitude, pos.coords.longitude, 10)
          // T3.11.07 — the result lands in the "nearby" suggestion group rather
          // than in the search results, so there is one place where a list of
          // airports appears and one way it looks. Pressing the button is a
          // deliberate "start again from where I am", so the field is cleared:
          // leaving a stale code behind the suggestions would show the viewer
          // two different answers at once.
          setNearby(data)
          setCountryFilter(null)
          setCityFilter(null)
          setSubtitle(null)
          onChange('')
          setQuery('')
          setOpen(true)
        } catch { /* silent */ }
        finally { setGeoLoading(false) }
      },
      () => setGeoLoading(false),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
  }

  const pickCountry = (row: CountryRow) => {
    setCountryFilter({ iso: row.iso, name: row.name })
    setCityFilter(null)
    setQuery('')
    setOpen(true)
  }

  const pickCity = (c: CityMatch) => {
    const name = displayNames.of(c.iso) ?? c.iso
    setCountryFilter({ iso: c.iso, name })
    setCityFilter({ iso: c.iso, city: c.city })
    setQuery('')
    setOpen(true)
  }

  const pickAirport = (a: Airport) => {
    const name = displayNames.of(a.country_iso) ?? a.country
    setSubtitle({ iso: a.country_iso, countryName: name, city: a.city })
    setCountryFilter(null)
    setCityFilter(null)
    onChange(a.iata)
    setQuery(a.iata)
    setOpen(false)
    // T3.11.07 — every pick teaches the next empty field.
    rememberAirport(a)
    setRecent(loadRecent())
  }

  const clearAll = () => {
    setCountryFilter(null)
    setCityFilter(null)
    setSubtitle(null)
    onChange('')
    setQuery('')
  }

  const chip = subtitle
    ? `${isoToFlag(subtitle.iso)} ${subtitle.iso} · ${subtitle.city}`
    : countryFilter
    ? cityFilter
      ? `${isoToFlag(countryFilter.iso)} ${countryFilter.name} · ${cityFilter.city}`
      : `${isoToFlag(countryFilter.iso)} ${countryFilter.name}`
    : null

  // T3.11.07 — suggestions replace the empty dropdown, they never compete with
  // a search. The moment there is a query, or a country/city has been picked,
  // the list is about that and nothing else.
  const suggesting = open && !query.trim() && !countryFilter && !cityFilter
  // Deduplicated across the three groups in order of confidence: the same
  // airport listed twice under two headings reads as two different answers.
  const suggestionGroups = useMemo(() => {
    if (!suggesting) return []
    const seen = new Set<string>()
    const take = (list: Airport[]) => {
      const out: Airport[] = []
      for (const a of list) {
        if (seen.has(a.iata)) continue
        seen.add(a.iata)
        out.push(a)
      }
      return out
    }
    return (
      [
        ['airports.groupRecent', take(recent)] as const,
        ['airports.groupPopular', take(popular)] as const,
        ['airports.groupNearby', take(nearby)] as const,
      ] as const
    ).filter(([, list]) => list.length > 0)
  }, [suggesting, recent, popular, nearby])

  /** T3.11.07 — one portal, one set of styles, two callers (the suggestions and
   *  the search results). Returns `null` until the field has been measured, so
   *  the panel never paints for a frame at the top-left corner.
   *
   *  Called by: the two dropdown blocks in this component's render. */
  const renderPanel = (children: React.ReactNode) => {
    if (!anchor) return null
    return createPortal(
      <div
        ref={panelRef}
        style={{
          position: 'fixed',
          left: anchor.left,
          width: anchor.width,
          top: anchor.top,
          transform: anchor.openUp ? 'translateY(-100%)' : undefined,
        }}
        className={`z-popover bg-white border border-navy/15 rounded-field shadow-md max-h-72 overflow-y-auto ${
          anchor.openUp ? '-mt-1' : 'mt-1'
        }`}
      >
        {children}
      </div>,
      document.body,
    )
  }

  const inputPlaceholder =
    cityFilter
      ? t('airports.typeIata', { defaultValue: 'Airport IATA' })
      : countryFilter
      ? t('airports.typeCity', { defaultValue: 'City' })
      : placeholder ?? t('airports.typeCountryCityIata', { defaultValue: 'Country / city / IATA' })

  return (
    <div ref={wrapperRef} className="relative">
      {chip && (
        <div className="mb-1 flex items-center gap-2">
          <span className="text-[11px] font-body font-bold text-navy/70 tracking-wide">
            {chip}
          </span>
          <button
            type="button"
            onClick={clearAll}
            className="text-[11px] font-body text-navy/40 hover:text-navy/70"
          >
            ×
          </button>
        </div>
      )}

      <div className="flex gap-1">
        <input
          id={inputId}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
            if (!countryFilter && !cityFilter) onChange(e.target.value.toUpperCase())
          }}
          onFocus={() => setOpen(true)}
          placeholder={inputPlaceholder}
          required={required}
          autoCapitalize={cityFilter || countryFilter ? 'sentences' : 'characters'}
          autoCorrect="off"
          spellCheck={false}
          className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
        />
        <button
          type="button"
          onClick={handleGeolocation}
          disabled={geoLoading}
          title={t('trips.useGeolocation', { defaultValue: 'Use my location' })}
          className="border border-navy/20 rounded-field px-2 min-h-[2.75rem] text-navy/60 hover:text-navy hover:border-cyan transition-colors disabled:opacity-50 flex items-center justify-center"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M22 12h-3M5 12H2" />
          </svg>
        </button>
      </div>

      {suggestionGroups.length > 0 &&
        renderPanel(
          <>
            {suggestionGroups.map(([labelKey, list]) => (
            <div key={labelKey}>
              <div className="px-3 py-1 text-[10px] font-body font-semibold text-navy/40 uppercase tracking-wider bg-ivory">
                {t(labelKey)}
              </div>
              {list.map((a) => (
                <button
                  key={`${labelKey}-${a.iata}`}
                  type="button"
                  onClick={() => pickAirport(a)}
                  className="w-full text-left px-3 py-2 hover:bg-ivory border-b border-navy/5 last:border-0 text-sm"
                >
                  <span className="font-mono font-bold text-navy">{a.iata}</span>
                  <span className="text-navy/60 ml-2">{a.city} · {a.country_iso}</span>
                </button>
              ))}
            </div>
          ))}
          </>,
        )}

      {open && !suggesting && (countryMatches.length > 0 || cityMatches.length > 0 || airportMatches.length > 0) &&
        renderPanel(
          <>
          {countryMatches.length > 0 && (
            <div>
              <div className="px-3 py-1 text-[10px] font-body font-semibold text-navy/40 uppercase tracking-wider bg-ivory">
                {t('airports.groupCountries', { defaultValue: 'Countries' })}
              </div>
              {countryMatches.map((c) => (
                <button
                  key={c.iso}
                  type="button"
                  onClick={() => pickCountry(c)}
                  className="w-full text-left px-3 py-2 hover:bg-ivory border-b border-navy/5 text-sm flex items-center justify-between"
                >
                  <span className="text-navy">
                    <span className="mr-2">{isoToFlag(c.iso)}</span>
                    {c.name}
                  </span>
                  <span className="font-mono text-xs text-navy/40">{c.iso}</span>
                </button>
              ))}
            </div>
          )}
          {cityMatches.length > 0 && (
            <div>
              <div className="px-3 py-1 text-[10px] font-body font-semibold text-navy/40 uppercase tracking-wider bg-ivory">
                {t('airports.groupCities', { defaultValue: 'Cities' })}
              </div>
              {cityMatches.map((c) => (
                <button
                  key={`${c.iso}-${c.city}`}
                  type="button"
                  onClick={() => pickCity(c)}
                  className="w-full text-left px-3 py-2 hover:bg-ivory border-b border-navy/5 text-sm flex items-center justify-between"
                >
                  <span className="text-navy">
                    <span className="mr-2">{isoToFlag(c.iso)}</span>
                    {c.city}
                  </span>
                  <span className="font-mono text-xs text-navy/40">{c.count} airp.</span>
                </button>
              ))}
            </div>
          )}
          {airportMatches.length > 0 && (
            <div>
              <div className="px-3 py-1 text-[10px] font-body font-semibold text-navy/40 uppercase tracking-wider bg-ivory">
                {t('airports.groupAirports', { defaultValue: 'Airports' })}
              </div>
              {airportMatches.map((a) => (
                <button
                  key={`${a.iata}-${a.lat}-${a.lon}`}
                  type="button"
                  onClick={() => pickAirport(a)}
                  className="w-full text-left px-3 py-2 hover:bg-ivory border-b border-navy/5 last:border-0 text-sm"
                >
                  <span className="font-mono font-bold text-navy">{a.iata}</span>
                  <span className="text-navy/60 ml-2">{a.city} · {a.country_iso}</span>
                </button>
              ))}
            </div>
          )}
          </>,
        )}
    </div>
  )
}
