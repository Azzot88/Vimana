import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listCategories, type Category } from '../api/categories'

interface Props {
  value: string
  onChange: (nameKey: string) => void
  placeholder?: string
}

export default function CategorySelect({ value, onChange, placeholder }: Props) {
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
