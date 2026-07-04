import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { nearestAirports, searchAirports, type Airport } from '../api/airports'
import AirportCascadeModal from './AirportCascadeModal'

interface Props {
  value: string
  onChange: (iata: string) => void
  placeholder?: string
  required?: boolean
}

export default function AirportSelect({ value, onChange, placeholder, required }: Props) {
  const { t } = useTranslation()
  const [query, setQuery] = useState(value)
  const [results, setResults] = useState<Airport[]>([])
  const [open, setOpen] = useState(false)
  const [geoLoading, setGeoLoading] = useState(false)
  const [cascadeOpen, setCascadeOpen] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

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
    if (!query.trim()) {
      setResults([])
      return
    }
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const { data } = await searchAirports(query)
        if (!cancelled) setResults(data)
      } catch {
        if (!cancelled) setResults([])
      }
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  const handleGeolocation = () => {
    if (!navigator.geolocation) return
    setGeoLoading(true)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const { data } = await nearestAirports(pos.coords.latitude, pos.coords.longitude, 10)
          setResults(data)
          setOpen(true)
        } catch { /* silent */ }
        finally { setGeoLoading(false) }
      },
      () => setGeoLoading(false),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
  }

  const pick = (a: Airport) => {
    onChange(a.iata)
    setQuery(a.iata)
    setOpen(false)
  }

  return (
    <div ref={wrapperRef} className="relative">
      <div className="flex gap-1">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value.toUpperCase())
            setOpen(true)
            onChange(e.target.value.toUpperCase())
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder ?? 'DXB'}
          required={required}
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          className="w-full border border-navy/20 rounded-lg px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan transition-colors"
        />
        <button
          type="button"
          onClick={handleGeolocation}
          disabled={geoLoading}
          title={t('trips.useGeolocation', { defaultValue: 'Use my location' })}
          className="border border-navy/20 rounded-lg px-2 text-navy/60 hover:text-navy hover:border-cyan transition-colors disabled:opacity-50 flex items-center justify-center"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M22 12h-3M5 12H2" />
          </svg>
        </button>
      </div>

      {open && results.length > 0 && (
        <ul className="absolute z-10 left-0 right-0 mt-1 bg-white border border-navy/15 rounded-lg shadow-md max-h-[9rem] overflow-y-auto">
          {results.map((a) => (
            <li
              key={`${a.iata}-${a.lat}-${a.lon}`}
              onClick={() => pick(a)}
              className="px-3 py-2 cursor-pointer hover:bg-ivory border-b border-navy/5 last:border-0 text-sm"
            >
              <span className="font-mono font-bold text-navy">{a.iata}</span>
              <span className="text-navy/60 ml-2">
                {a.city}, {a.country}
              </span>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={() => setCascadeOpen(true)}
        className="mt-1 text-xs font-body text-cyan/70 hover:text-cyan hover:underline"
      >
        {t('airports.notWorking', { defaultValue: 'Not working? Pick country → city →' })}
      </button>

      {cascadeOpen && (
        <AirportCascadeModal
          onPick={(iata) => { onChange(iata); setQuery(iata) }}
          onClose={() => setCascadeOpen(false)}
        />
      )}
    </div>
  )
}
