import { useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { searchCities, type City } from '../api/cities'

export interface AddressFormValue {
  label: string
  country_iso: string
  city: string | null
  city_geoname_id: number | null
  street: string | null
  postal_code: string | null
  note: string | null
}

interface Props {
  value: AddressFormValue
  onChange: (patch: Partial<AddressFormValue>) => void
  countryOptions: Array<{ iso: string; name: string }>
}

/** T_UX.4 B — pure form fields for a single ReceivingAddress. No API
 *  calls, no wrapper card — parent owns list state and Save button. */
export default function AddressFormFields({ value, onChange, countryOptions }: Props) {
  const { t, i18n } = useTranslation()
  const [cityQuery, setCityQuery] = useState(value.city ?? '')
  const [suggestions, setSuggestions] = useState<City[]>([])
  const [showSuggest, setShowSuggest] = useState(false)

  useEffect(() => {
    setCityQuery(value.city ?? '')
  }, [value.city])

  useEffect(() => {
    if (!cityQuery.trim() || !value.country_iso) {
      setSuggestions([])
      return
    }
    const controller = new AbortController()
    const timeoutId = setTimeout(async () => {
      try {
        const { data } = await searchCities({ q: cityQuery, country: value.country_iso })
        if (!controller.signal.aborted) setSuggestions(data)
      } catch { /* silent */ }
    }, 200)
    return () => {
      controller.abort()
      clearTimeout(timeoutId)
    }
  }, [cityQuery, value.country_iso])

  const countryDisplay = new Intl.DisplayNames([i18n.language], { type: 'region' })

  // T_TEST.8 — a <label> that is a sibling of its field names nothing: the
  // association has to be written down. `useId` because two address forms can
  // be open at once, and fixed ids would point the second form's labels at the
  // first form's fields.
  const uid = useId()

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor={`${uid}-label`} className="block text-xs font-body font-medium text-muted mb-1">
          {t('address.label')}
        </label>
        <input
          id={`${uid}-label`}
          type="text"
          value={value.label}
          onChange={(e) => onChange({ label: e.target.value })}
          placeholder={t('address.labelPlaceholder') as string}
          maxLength={60}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
      </div>

      <div>
        <label htmlFor={`${uid}-country`} className="block text-xs font-body font-medium text-muted mb-1">
          {t('profile.address.country')}
        </label>
        <select
          id={`${uid}-country`}
          value={value.country_iso}
          onChange={(e) =>
            onChange({
              country_iso: e.target.value,
              city: null,
              city_geoname_id: null,
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
        <label htmlFor={`${uid}-city`} className="block text-xs font-body font-medium text-muted mb-1">
          {t('profile.address.city')}
        </label>
        <input
          id={`${uid}-city`}
          type="text"
          value={cityQuery}
          onChange={(e) => {
            setCityQuery(e.target.value)
            setShowSuggest(true)
            onChange({ city: e.target.value || null, city_geoname_id: null })
          }}
          onFocus={() => setShowSuggest(true)}
          onBlur={() => setTimeout(() => setShowSuggest(false), 150)}
          disabled={!value.country_iso}
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
                    onChange({ city: s.name, city_geoname_id: s.geoname_id })
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
        <label htmlFor={`${uid}-street`} className="block text-xs font-body font-medium text-muted mb-1">
          {t('profile.address.street')}
        </label>
        <input
          id={`${uid}-street`}
          type="text"
          value={value.street ?? ''}
          onChange={(e) => onChange({ street: e.target.value || null })}
          placeholder={t('profile.address.streetPlaceholder') as string}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
        />
      </div>

      <div>
        <label htmlFor={`${uid}-postal`} className="block text-xs font-body font-medium text-muted mb-1">
          {t('profile.address.postal')}
        </label>
        <input
          id={`${uid}-postal`}
          type="text"
          value={value.postal_code ?? ''}
          onChange={(e) => onChange({ postal_code: e.target.value || null })}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy focus:outline-none focus:border-cyan"
        />
      </div>

      <div>
        <label htmlFor={`${uid}-note`} className="block text-xs font-body font-medium text-muted mb-1">
          {t('profile.address.note')}
        </label>
        <textarea
          id={`${uid}-note`}
          value={value.note ?? ''}
          onChange={(e) => onChange({ note: e.target.value || null })}
          rows={2}
          maxLength={500}
          placeholder={t('profile.address.notePlaceholder') as string}
          className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan resize-none"
        />
      </div>
    </div>
  )
}
