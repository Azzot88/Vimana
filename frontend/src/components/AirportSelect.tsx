import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  airportsInCity,
  listCitiesInCountry,
  listCountries,
  lookupAirports,
  nearestAirports,
  type Airport,
  type CityMatch,
  type CountryCount,
} from '../api/airports'

interface Props {
  value: string
  onChange: (iata: string) => void
  placeholder?: string
  required?: boolean
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

export default function AirportSelect({ value, onChange, placeholder, required }: Props) {
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
  const wrapperRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    setQuery(value)
  }, [value])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

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
          setAirportMatches(data)
          setCityMatches([])
          setCountryMatches([])
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

      {open && (countryMatches.length > 0 || cityMatches.length > 0 || airportMatches.length > 0) && (
        <div className="absolute z-20 left-0 right-0 mt-1 bg-white border border-navy/15 rounded-field shadow-md max-h-72 overflow-y-auto">
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
        </div>
      )}
    </div>
  )
}
