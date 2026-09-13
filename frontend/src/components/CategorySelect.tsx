import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listCategories, type Category } from '../api/categories'

interface Props {
  value: string
  onChange: (nameKey: string) => void
  placeholder?: string
  /** T3.11.07 — the categories this trip actually carries (owner's rule
   *  2026-09-08: «в заявке появляется только то что есть в опубликованном
   *  рейсе»). Given a list, the field stops being a search over the whole
   *  catalogue and becomes a pick from what the carrier offered — no free text,
   *  because a category the carrier never named is a parcel they never agreed
   *  to take, and the server refuses it with a 409.
   *
   *  An empty list or none at all keeps the search: `allowed_categories` is
   *  optional on a trip so that a route and a date can publish one, and reading
   *  silence as «carries nothing» would make every express listing unbookable. */
  only?: string[]
  /** T3.11.27 (owner, 2026-09-12): «должно быть больше категорий, все
   *  категории».
   *
   *  A request is a pick, never an invention. With no `only` the field used to
   *  fall back to the carrier's own tool — a search box over the catalogue with
   *  «+ Use "…"» under it — which on the sender's side asks somebody to guess
   *  words at an empty input and lets them invent a category the carrier never
   *  agreed to carry. Set here, the whole active catalogue is drawn as chips
   *  instead: the same shape as a narrowed trip, just wider.
   *
   *  The carrier's side keeps the search and the custom entry. That is where a
   *  new word legitimately enters the vocabulary — somebody states what they
   *  are actually willing to carry. */
  catalogue?: boolean
}

export default function CategorySelect({
  value,
  onChange,
  placeholder,
  only,
  catalogue,
}: Props) {
  const { t } = useTranslation()
  const [query, setQuery] = useState(value)
  const [results, setResults] = useState<Category[]>([])
  const [open, setOpen] = useState(false)
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
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const { data } = await listCategories(query)
        if (!cancelled) setResults(data)
      } catch {
        if (!cancelled) setResults([])
      }
    }, 150)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  const label = (key: string): string => {
    const translated = t(`categories.${key}`, { defaultValue: '' })
    return translated || key
  }

  const pick = (key: string) => {
    onChange(key)
    setQuery(key)
    setOpen(false)
  }

  const submitCustom = () => {
    const custom = query.trim().toLowerCase()
    if (custom) {
      onChange(custom)
      setOpen(false)
    }
  }

  const exactMatch = results.some((r) => r.name_key === query.trim().toLowerCase())
  const canAddNew = query.trim().length > 0 && !exactMatch

  /* Chips rather than a dropdown, whether the list is one carrier's offer or
     the whole catalogue: both are short enough to read at a glance, and a
     select that holds seven items is a click spent hiding six of them. */
  const chips =
    only && only.length > 0
      ? only
      : catalogue
        ? results.map((r) => r.name_key)
        : null
  if (chips) {
    return (
      <div className="flex flex-wrap gap-2">
        {chips.map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={value === key}
            onClick={() => onChange(key)}
            className={`text-xs font-body px-3 py-2 min-h-[2.75rem] rounded-field border transition-colors ${
              value === key
                ? 'border-cyan bg-cyan/10 text-navy'
                : 'border-navy/20 text-navy/50 hover:border-navy/40'
            }`}
          >
            {label(key)}
          </button>
        ))}
      </div>
    )
  }

  return (
    <div ref={wrapperRef} className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && canAddNew) {
            e.preventDefault()
            submitCustom()
          }
        }}
        placeholder={placeholder ?? t('categories.placeholder', { defaultValue: 'Category or custom…' })}
        className="w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-body text-navy focus:outline-none focus:border-cyan transition-colors"
      />
      {open && (results.length > 0 || canAddNew) && (
        <ul className="absolute z-10 left-0 right-0 mt-1 bg-white border border-navy/15 rounded-field shadow-md max-h-56 overflow-y-auto">
          {results.map((c) => (
            <li key={c.name_key}>
              <button
                type="button"
                onClick={() => pick(c.name_key)}
                className="w-full text-left px-3 py-2 hover:bg-ivory border-b border-navy/5 text-sm flex items-center justify-between"
              >
                <span className="text-navy">
                  {label(c.name_key)}
                  {!c.is_default && (
                    <span className="ml-2 text-[10px] font-mono text-navy/40">custom</span>
                  )}
                </span>
                {c.usage_count > 0 && (
                  <span className="text-[10px] font-mono text-navy/40">{c.usage_count}</span>
                )}
              </button>
            </li>
          ))}
          {canAddNew && (
            <li>
              <button
                type="button"
                onClick={submitCustom}
                className="w-full text-left px-3 py-2 hover:bg-ivory text-sm text-cyan"
              >
                {t('categories.addNew', { defaultValue: '+ Use' })} "{query.trim().toLowerCase()}"
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
