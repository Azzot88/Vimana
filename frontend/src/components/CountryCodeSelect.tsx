import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getCountries, getCountryCallingCode } from 'libphonenumber-js/min'
import type { CountryCode } from 'libphonenumber-js/min'

interface Props {
  value: CountryCode | ''
  onChange: (iso: CountryCode) => void
}

function isoToFlag(iso: string): string {
  return iso
    .toUpperCase()
    .replace(/./g, (c) => String.fromCodePoint(127397 + c.charCodeAt(0)))
}

interface CountryRow {
  iso: CountryCode
  name: string
  dial: string
}

export default function CountryCodeSelect({ value, onChange }: Props) {
  const { i18n, t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const wrapperRef = useRef<HTMLDivElement>(null)

  const displayNames = useMemo(
    () => new Intl.DisplayNames([i18n.language], { type: 'region' }),
    [i18n.language],
  )

  const countries: CountryRow[] = useMemo(() => {
    const list: CountryRow[] = []
    for (const iso of getCountries()) {
      const name = displayNames.of(iso) ?? iso
      let dial = ''
      try {
        dial = getCountryCallingCode(iso)
      } catch {
        continue
      }
      list.push({ iso, name, dial })
    }
    return list.sort((a, b) => a.name.localeCompare(b.name, i18n.language))
  }, [displayNames, i18n.language])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return countries
    return countries.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.iso.toLowerCase().includes(q) ||
        c.dial.startsWith(q.replace(/^\+/, '')),
    )
  }, [countries, query])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const selectedDial = value ? getCountryCallingCode(value as CountryCode) : ''
  const selectedLabel = value
    ? `${isoToFlag(value)} +${selectedDial}`
    : t('profile.phoneSelectCountry', { defaultValue: 'Select…' })

  const pick = (iso: CountryCode) => {
    onChange(iso)
    setOpen(false)
    setQuery('')
  }

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="border border-navy/20 rounded-field px-3 py-2 text-sm font-mono text-navy hover:border-cyan transition-colors min-w-[6rem] text-left"
      >
        {selectedLabel}
      </button>

      {open && (
        <div className="absolute z-10 mt-1 left-0 bg-white border border-navy/15 rounded-field shadow-md w-72">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('profile.phoneSearchCountry', { defaultValue: 'Search country…' })}
            autoFocus
            className="w-full border-b border-navy/10 px-3 py-2 text-sm font-body text-navy focus:outline-none"
          />
          <ul className="max-h-64 overflow-y-auto">
            {filtered.map((c) => (
              <li
                key={c.iso}
                onClick={() => pick(c.iso)}
                className="px-3 py-2 cursor-pointer hover:bg-ivory text-sm flex items-center justify-between border-b border-navy/5 last:border-0"
              >
                <span className="flex items-center gap-2">
                  <span className="text-base">{isoToFlag(c.iso)}</span>
                  <span className="text-navy">{c.name}</span>
                </span>
                <span className="font-mono text-muted">+{c.dial}</span>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="px-3 py-4 text-sm text-muted text-center font-body">—</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
