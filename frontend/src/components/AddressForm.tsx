import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { searchCities, type City } from '../api/cities'

interface AddressFormValue {
  receiving_country_iso: string | null
  receiving_city: string | null
  receiving_city_geoname_id: number | null
  receiving_street: string | null
  receiving_postal_code: string | null
  receiving_note: string | null
}

interface Props {
  value: AddressFormValue
  onChange: (patch: Partial<AddressFormValue>) => void
  countryOptions: Array<{ iso: string; name: string }>
}

export default function AddressForm({ value, onChange, countryOptions }: Props) {
  const { t, i18n } = useTranslation()
  const [cityQuery, setCityQuery] = useState(value.receiving_city ?? '')
  const [suggestions, setSuggestions] = useState<City[]>([])
  const [showSuggest, setShowSuggest] = useState(false)

  useEffect(() => {
    setCityQuery(value.receiving_city ?? '')
  }, [value.receiving_city])

  useEffect(() => {
    if (!cityQuery.trim() || !value.receiving_country_iso) {
      setSuggestions([])
      return
    }
    const controller = new AbortController()
    const timeoutId = setTimeout(async () => {
      try {
        const { data } = await searchCities({
          q: cityQuery,
          country: value.receiving_country_iso!,
        })
        if (!controller.signal.aborted) setSuggestions(data)
      } catch {
        // ignore
      }
    }, 200)
    return () => {
      controller.abort()
      clearTimeout(timeoutId)
    }
  }, [cityQuery, value.receiving_country_iso])

  const countryDisplay = new Intl.DisplayNames([i18n.language], { type: 'region' })

  return (
    <div className="space-y-3">
      <p className="text-xs font-mono text-navy/40">
        🔒 {t('profile.address.privacyHint')}
      </p>

      <div>
        <label className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('profile.address.country')}
        </label>
        <select
          value={value.receiving_country_iso ?? ''}
          onChange={(e) =>
            onChange({
              receiving_country_iso: e.target.value || null,
              receiving_city: null,
              receiving_city_geoname_id: null,
            })
          }
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy bg-white focus:outline-none focus:border-cyan"
        >
          <option value="">—</option>
          {countryOptions.map((c) => (
            <option key={c.iso} value={c.iso}>
              {c.name || countryDisplay.of(c.iso) || c.iso}
            </option>
          ))}
        </select>
      </div>

      <div className="relative">
        <label className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('profile.address.city')}
        </label>
        <input
          type="text"
          value={cityQuery}
          onChange={(e) => {
            setCityQuery(e.target.value)
            setShowSuggest(true)
            onChange({
              receiving_city: e.target.value || null,
              receiving_city_geoname_id: null,
            })
          }}
          onFocus={() => setShowSuggest(true)}
          onBlur={() => setTimeout(() => setShowSuggest(false), 150)}
          disabled={!value.receiving_country_iso}
          placeholder={t('profile.address.cityPlaceholder') as string}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan disabled:opacity-50"
        />
        {showSuggest && suggestions.length > 0 && (
          <ul className="absolute z-10 mt-1 w-full bg-white border border-navy/20 rounded-field shadow-lg max-h-48 overflow-y-auto">
            {suggestions.map((s) => (
              <li key={s.geoname_id}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    setCityQuery(s.name)
                    onChange({
                      receiving_city: s.name,
                      receiving_city_geoname_id: s.geoname_id,
                    })
                    setShowSuggest(false)
                  }}
                  className="w-full text-left px-3 py-2 text-sm font-body text-navy hover:bg-ivory"
                >
                  {s.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <label className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('profile.address.street')}
        </label>
        <input
          type="text"
          value={value.receiving_street ?? ''}
          onChange={(e) => onChange({ receiving_street: e.target.value || null })}
          placeholder={t('profile.address.streetPlaceholder') as string}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
      </div>

      <div>
        <label className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('profile.address.postal')}
        </label>
        <input
          type="text"
          value={value.receiving_postal_code ?? ''}
          onChange={(e) => onChange({ receiving_postal_code: e.target.value || null })}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
        />
      </div>

      <div>
        <label className="block text-xs font-body font-medium text-navy/60 mb-1">
          {t('profile.address.note')}
        </label>
        <textarea
          value={value.receiving_note ?? ''}
          onChange={(e) => onChange({ receiving_note: e.target.value || null })}
          rows={2}
          maxLength={500}
          placeholder={t('profile.address.notePlaceholder') as string}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan resize-none"
        />
      </div>
    </div>
  )
}
