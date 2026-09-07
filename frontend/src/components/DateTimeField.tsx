import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { intlLocale, type DateStyle } from '../lib/format'
import MonoText from './MonoText'

/** T3.11.07 — a date and time picker we actually own.
 *
 *  It replaces `<input type="datetime-local">`, and the reason is not taste.
 *  The native control is drawn by the browser: it takes 12- or 24-hour from the
 *  **device** locale, and no attribute overrides that. So a carrier who set
 *  "European" in their profile still got `02:30 PM` inside the calendar, which
 *  made the account setting look broken — it was being honoured everywhere we
 *  paint pixels and nowhere the browser does. The same wall stopped us
 *  translating the calendar, moving its buttons or putting a "Save" on it.
 *
 *  So the value keeps the `datetime-local` wire shape — `YYYY-MM-DDTHH:mm`, no
 *  timezone, exactly what the API and the rest of the form already pass around
 *  — and only the drawing changes.
 *
 *  **Month and weekday names come from `Intl`, not from our locale files.**
 *  Names are a property of the language, and `Intl` already has all six of
 *  ours; twelve months × six languages typed by hand is a translation table
 *  that starts correct and rots. The *format* is a separate setting and stays
 *  ours: `date_format` decides day-month order, the clock, and which day starts
 *  the week.
 *
 *  Called by: `pages/NewTripPage` (every stop on the route).
 */
interface DateTimeFieldProps {
  id?: string
  /** `YYYY-MM-DDTHH:mm`, or empty for "not chosen". */
  value: string
  onChange: (value: string) => void
  /** The account's date style — decides the clock and the first day of week. */
  style: DateStyle
  /** Earliest selectable day, same shape. Days before it are disabled. */
  min?: string
  required?: boolean
  ariaLabel?: string
}

const pad = (n: number) => String(n).padStart(2, '0')

/** `Date` → the wire shape. Local time on purpose: the carrier means the clock
 *  on the wall at the airport they are leaving from, not UTC. */
function toValue(d: Date, hours: number, minutes: number): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    hours,
  )}:${pad(minutes)}`
}

/** The wire shape → `Date`, or `null` for empty and unparseable alike. Both
 *  mean "nothing chosen yet" to every caller. */
function parseValue(value: string): Date | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Midnight of the day `value` names, for comparing days without the clock. */
const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate())

export default function DateTimeField({
  id,
  value,
  onChange,
  style,
  min,
  required,
  ariaLabel,
}: DateTimeFieldProps) {
  const { t, i18n } = useTranslation()
  const locale = style === 'us' ? 'en-US' : intlLocale(i18n.language)
  const hour12 = style === 'us'
  // European weeks start on Monday, American ones on Sunday. It follows from
  // the same setting rather than from a switch of its own: somebody who reads
  // dates one way reads calendars the same way.
  const weekStart = style === 'us' ? 0 : 1

  const [open, setOpen] = useState(false)
  // Edits live here until "Save": a calendar that writes on every click cannot
  // offer a Save button that means anything, and the carrier who opened it to
  // look would leave with a changed date.
  const [draft, setDraft] = useState<Date | null>(null)
  const [month, setMonth] = useState<Date>(() => startOfDay(new Date()))
  const [anchor, setAnchor] = useState<{ top: number; left: number; width: number } | null>(
    null,
  )
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  const selected = useMemo(() => parseValue(value), [value])
  const minDay = useMemo(() => {
    const d = parseValue(min ?? '')
    return d ? startOfDay(d) : null
  }, [min])

  // Opening starts from what is already chosen, or from now rounded up to the
  // next half hour — a departure at 14:37 is a time nobody types.
  const openPicker = () => {
    const base = selected ?? roundedNow()
    setDraft(base)
    setMonth(startOfDay(base))
    const box = triggerRef.current?.getBoundingClientRect()
    if (box) {
      setAnchor({ top: box.bottom + window.scrollY + 4, left: box.left + window.scrollX, width: box.width })
    }
    setOpen(true)
  }

  // Portalled to `body` for the same reason `AirportSelect` is: the field sits
  // inside a scrolling sheet, and a popover that is a child of it gets clipped
  // by the first ancestor with `overflow`.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    const onPointer = (e: MouseEvent) => {
      const target = e.target as Node
      if (popoverRef.current?.contains(target) || triggerRef.current?.contains(target)) {
        return
      }
      setOpen(false)
    }
    document.addEventListener('keydown', onKey, true)
    document.addEventListener('mousedown', onPointer)
    // The popover is portalled to the end of `body`, so tabbing out of the
    // trigger walks into the next form field instead of into the calendar.
    // Moving focus here is what makes Escape and the arrow keys reach the
    // thing the carrier just opened.
    popoverRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey, true)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [open])

  const monthLabel = useMemo(
    () =>
      month.toLocaleDateString(locale, { month: 'long', year: 'numeric' }),
    [month, locale],
  )

  // Seven short names starting on the account's first day. Built from a known
  // week rather than hardcoded: 2024-01-01 was a Monday, so the offsets are
  // stable and the names come out in whatever language is on.
  const weekdays = useMemo(() => {
    const monday = new Date(2024, 0, 1)
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(monday)
      d.setDate(monday.getDate() + ((i + weekStart + 6) % 7))
      return d.toLocaleDateString(locale, { weekday: 'short' })
    })
  }, [locale, weekStart])

  /** The cells of the visible month, padded to whole weeks with nulls. */
  const cells = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1)
    const lead = (first.getDay() - weekStart + 7) % 7
    const days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
    const out: (Date | null)[] = Array.from({ length: lead }, () => null)
    for (let day = 1; day <= days; day += 1) {
      out.push(new Date(month.getFullYear(), month.getMonth(), day))
    }
    while (out.length % 7 !== 0) out.push(null)
    return out
  }, [month, weekStart])

  const today = startOfDay(new Date())
  const draftDay = draft ? startOfDay(draft) : null
  const isDisabled = (d: Date) => (minDay ? startOfDay(d) < minDay : false)

  const pickDay = (d: Date) => {
    const keep = draft ?? roundedNow()
    setDraft(new Date(d.getFullYear(), d.getMonth(), d.getDate(), keep.getHours(), keep.getMinutes()))
  }

  const setClock = (hours: number, minutes: number) => {
    const base = draft ?? roundedNow()
    setDraft(new Date(base.getFullYear(), base.getMonth(), base.getDate(), hours, minutes))
  }

  const save = () => {
    if (!draft) return
    onChange(toValue(draft, draft.getHours(), draft.getMinutes()))
    setOpen(false)
    triggerRef.current?.focus()
  }

  const clear = () => {
    onChange('')
    setOpen(false)
    triggerRef.current?.focus()
  }

  /** Jump to today without choosing it: it moves the calendar and the draft to
   *  now, and the carrier still presses Save. */
  const goToday = () => {
    const now = roundedNow()
    setDraft(now)
    setMonth(startOfDay(now))
  }

  const shown = selected
    ? selected.toLocaleString(locale, {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12,
      })
    : ''

  // 12-hour clocks are edited as 1–12 plus a meridiem; 24-hour ones as 0–23.
  // Storing is the same either way — the draft is a real `Date`.
  const hours24 = draft?.getHours() ?? 0
  const displayHour = hour12 ? ((hours24 % 12) || 12) : hours24
  const meridiem = hours24 >= 12 ? 'pm' : 'am'

  return (
    <>
      <button
        id={id}
        ref={triggerRef}
        type="button"
        onClick={() => (open ? setOpen(false) : openPicker())}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel}
        aria-required={required}
        className={`w-full border border-navy/20 rounded-field px-3 py-2 min-h-[2.75rem] text-sm font-mono text-left focus:outline-none focus:border-cyan ${
          shown ? 'text-navy' : 'text-navy/35'
        }`}
      >
        {shown || t('trips.pickDateTime')}
      </button>

      {open &&
        anchor &&
        createPortal(
          <div
            ref={popoverRef}
            role="dialog"
            aria-label={t('trips.pickDateTime') as string}
            tabIndex={-1}
            style={{ top: anchor.top, left: anchor.left, minWidth: Math.max(anchor.width, 288) }}
            className="absolute z-popover w-72 rounded-card border border-navy/15 bg-white shadow-lift p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}
                aria-label={t('calendar.prevMonth') as string}
                className="w-8 h-8 rounded-field border border-navy/15 text-navy/60 hover:border-cyan hover:text-navy"
              >
                ‹
              </button>
              {/* Capitalised because several of our languages give a lowercase
                  month name and a heading that starts small reads as a typo. */}
              <span className="text-sm font-display font-semibold text-navy first-letter:uppercase">
                {monthLabel}
              </span>
              <button
                type="button"
                onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}
                aria-label={t('calendar.nextMonth') as string}
                className="w-8 h-8 rounded-field border border-navy/15 text-navy/60 hover:border-cyan hover:text-navy"
              >
                ›
              </button>
            </div>

            <div className="grid grid-cols-7 gap-0.5 mt-3" aria-hidden="true">
              {weekdays.map((name) => (
                <span
                  key={name}
                  className="text-[10px] font-body text-navy/40 text-center py-1 first-letter:uppercase"
                >
                  {name}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-0.5">
              {cells.map((day, i) => {
                if (!day) return <span key={`pad-${i}`} />
                const isToday = startOfDay(day).getTime() === today.getTime()
                const isPicked =
                  draftDay && startOfDay(day).getTime() === draftDay.getTime()
                const disabled = isDisabled(day)
                return (
                  <button
                    key={day.toISOString()}
                    type="button"
                    onClick={() => pickDay(day)}
                    disabled={disabled}
                    aria-pressed={Boolean(isPicked)}
                    className={`h-8 rounded-field text-xs font-mono transition-colors disabled:opacity-25 disabled:cursor-not-allowed ${
                      isPicked
                        ? 'bg-cyan text-white'
                        : isToday
                          ? 'border border-cyan/50 text-navy hover:bg-cyan/10'
                          : 'text-navy/70 hover:bg-navy/5'
                    }`}
                  >
                    {day.getDate()}
                  </button>
                )
              })}
            </div>

            <div className="flex items-center gap-2 mt-3 pt-3 border-t border-navy/10">
              <span className="text-[11px] font-body text-navy/50">
                {t('calendar.time')}
              </span>
              <input
                type="number"
                min={hour12 ? 1 : 0}
                max={hour12 ? 12 : 23}
                value={pad(displayHour)}
                onChange={(e) => {
                  // An emptied box is mid-edit, not midnight: `Number("")` is 0,
                  // and writing it would move the hour under the cursor.
                  if (e.target.value === '') return
                  const raw = Number(e.target.value)
                  if (Number.isNaN(raw)) return
                  const h24 = hour12
                    ? (raw % 12) + (meridiem === 'pm' ? 12 : 0)
                    : Math.min(23, Math.max(0, raw))
                  setClock(h24, draft?.getMinutes() ?? 0)
                }}
                aria-label={t('calendar.hours') as string}
                className="w-14 border border-navy/20 rounded-field px-2 py-1.5 text-sm font-mono text-navy text-center focus:outline-none focus:border-cyan"
              />
              <MonoText className="text-navy/40">:</MonoText>
              <input
                type="number"
                min={0}
                max={59}
                step={5}
                value={pad(draft?.getMinutes() ?? 0)}
                onChange={(e) => {
                  if (e.target.value === '') return
                  const raw = Number(e.target.value)
                  if (Number.isNaN(raw)) return
                  setClock(hours24, Math.min(59, Math.max(0, raw)))
                }}
                aria-label={t('calendar.minutes') as string}
                className="w-14 border border-navy/20 rounded-field px-2 py-1.5 text-sm font-mono text-navy text-center focus:outline-none focus:border-cyan"
              />
              {hour12 && (
                <div className="flex gap-1 ml-auto">
                  {(['am', 'pm'] as const).map((half) => (
                    <button
                      key={half}
                      type="button"
                      aria-pressed={meridiem === half}
                      onClick={() =>
                        setClock(
                          (hours24 % 12) + (half === 'pm' ? 12 : 0),
                          draft?.getMinutes() ?? 0,
                        )
                      }
                      className={`px-2 py-1.5 rounded-field border text-[11px] font-mono uppercase ${
                        meridiem === half
                          ? 'border-cyan bg-cyan/10 text-navy'
                          : 'border-navy/15 text-navy/50'
                      }`}
                    >
                      {half}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Three buttons, and the order is the owner's (2026-09-06): clear
                on the left, **today in the middle**, and Save where the native
                calendar used to put Today. The native one had no Save at all —
                it wrote on every click — which is exactly why a carrier who
                opened it to check a date left with a different one. */}
            <div className="grid grid-cols-3 gap-2 mt-3">
              <button
                type="button"
                onClick={clear}
                className="px-2 py-2 min-h-[2.5rem] rounded-field border border-navy/15 text-[11px] font-body text-navy/50 hover:text-danger hover:border-danger/40"
              >
                {t('calendar.clear')}
              </button>
              <button
                type="button"
                onClick={goToday}
                className="px-2 py-2 min-h-[2.5rem] rounded-field border border-navy/15 text-[11px] font-body text-navy/60 hover:border-cyan hover:text-navy"
              >
                {t('calendar.today')}
              </button>
              <button
                type="button"
                onClick={save}
                className="px-2 py-2 min-h-[2.5rem] rounded-field bg-cyan text-white text-[11px] font-body font-medium hover:bg-cyan/90"
              >
                {t('calendar.save')}
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  )
}

/** Now, rounded up to the next half hour. A departure at 14:37 is a time
 *  nobody types, and an opening value nobody wants is one more thing to fix. */
function roundedNow(): Date {
  const d = new Date()
  d.setSeconds(0, 0)
  d.setMinutes(d.getMinutes() > 30 ? 60 : 30)
  return d
}
