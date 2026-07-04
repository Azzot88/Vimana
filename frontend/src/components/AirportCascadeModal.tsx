import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  airportsInCity,
  listCitiesInCountry,
  listCountries,
  type Airport,
  type CityCount,
  type CountryCount,
} from '../api/airports'

interface Props {
  onPick: (iata: string) => void
  onClose: () => void
}

export default function AirportCascadeModal({ onPick, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const [step, setStep] = useState<'country' | 'city' | 'airport'>('country')
  const [countries, setCountries] = useState<CountryCount[]>([])
  const [selectedIso, setSelectedIso] = useState('')
  const [cities, setCities] = useState<CityCount[]>([])
  const [selectedCity, setSelectedCity] = useState('')
  const [airports, setAirports] = useState<Airport[]>([])
  const [query, setQuery] = useState('')

  const displayNames = useMemo(
    () => new Intl.DisplayNames([i18n.language], { type: 'region' }),
    [i18n.language],
  )
  const enDisplayNames = useMemo(
    () => new Intl.DisplayNames(['en'], { type: 'region' }),
    [],
  )

  useEffect(() => {
    listCountries().then((r) => setCountries(r.data)).catch(() => {})
  }, [])

  useEffect(() => {
    setQuery('')
  }, [step])

  const countryRows = useMemo(() => {
    return countries.map((c) => ({
      iso: c.iso,
      count: c.count,
      name: displayNames.of(c.iso) ?? c.iso,
      nameEn: enDisplayNames.of(c.iso) ?? c.iso,
    }))
  }, [countries, displayNames, enDisplayNames])

  const filteredCountries = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return countryRows
    return countryRows.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.nameEn.toLowerCase().includes(q) ||
        c.iso.toLowerCase().includes(q),
    )
  }, [countryRows, query])

  const filteredCities = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return cities
    return cities.filter((c) => c.city.toLowerCase().includes(q))
  }, [cities, query])

  const pickCountry = async (iso: string) => {
    setSelectedIso(iso)
    setStep('city')
    try {
      const { data } = await listCitiesInCountry(iso)
      setCities(data)
    } catch { setCities([]) }
  }

  const pickCity = async (city: string) => {
    setSelectedCity(city)
    try {
      const { data } = await airportsInCity(selectedIso, city)
      setAirports(data)
      if (data.length === 1) {
        onPick(data[0].iata)
        onClose()
        return
      }
      setStep('airport')
    } catch { setAirports([]) }
  }

  const goBack = () => {
    if (step === 'airport') setStep('city')
    else if (step === 'city') setStep('country')
  }

  return (
    <div className="fixed inset-0 z-50 bg-navy/40 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="bg-white w-full sm:max-w-md sm:rounded-xl rounded-t-2xl border border-navy/10 max-h-[85vh] flex flex-col">
        <div className="p-4 border-b border-navy/10 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {step !== 'country' && (
              <button
                onClick={goBack}
                className="text-navy/50 hover:text-navy text-sm"
                aria-label="back"
              >
                ←
              </button>
            )}
            <h3 className="font-display font-semibold text-navy">
              {step === 'country' && t('airports.selectCountry', { defaultValue: 'Select country' })}
              {step === 'city' && t('airports.selectCity', { defaultValue: 'Select city' })}
              {step === 'airport' && t('airports.selectAirport', { defaultValue: 'Select airport' })}
            </h3>
          </div>
          <button onClick={onClose} className="text-navy/50 hover:text-navy text-sm">
            ✕
          </button>
        </div>

        {step !== 'airport' && (
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('common.search', { defaultValue: 'Search…' })}
            autoFocus
            className="border-b border-navy/10 px-4 py-3 text-sm font-body text-navy focus:outline-none"
          />
        )}

        <ul className="flex-1 overflow-y-auto">
          {step === 'country' && filteredCountries.map((c) => (
            <li key={c.iso}>
              <button
                type="button"
                onClick={() => pickCountry(c.iso)}
                className="w-full text-left px-4 py-3 min-h-[2.75rem] hover:bg-ivory border-b border-navy/5 flex items-center justify-between text-sm"
              >
                <span className="text-navy">{c.name}</span>
                <span className="font-mono text-xs text-navy/40">{c.iso} · {c.count}</span>
              </button>
            </li>
          ))}
          {step === 'city' && filteredCities.map((c) => (
            <li key={c.city}>
              <button
                type="button"
                onClick={() => pickCity(c.city)}
                className="w-full text-left px-4 py-3 min-h-[2.75rem] hover:bg-ivory border-b border-navy/5 flex items-center justify-between text-sm"
              >
                <span className="text-navy">{c.city}</span>
                <span className="font-mono text-xs text-navy/40">{c.count}</span>
              </button>
            </li>
          ))}
          {step === 'airport' && airports.map((a) => (
            <li key={a.iata}>
              <button
                type="button"
                onClick={() => { onPick(a.iata); onClose() }}
                className="w-full text-left px-4 py-3 min-h-[2.75rem] hover:bg-ivory border-b border-navy/5 text-sm"
              >
                <span className="font-mono font-bold text-navy">{a.iata}</span>
                <span className="text-navy/60 ml-2">{a.city}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
