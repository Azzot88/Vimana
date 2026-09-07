import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import {
  formatDate,
  formatDateTime,
  formatWeight,
  toDisplayWeight,
  toKilograms,
  type DateStyle,
  type WeightUnit,
} from '../lib/format'

/** T_UX.14 — one place that knows how this account reads numbers.
 *
 *  Every screen used to call `toLocaleString(i18n.language)` on its own, which
 *  tied the clock format to the interface language: a Russian-speaking carrier
 *  working a US corridor got a 24-hour clock whether or not that is what their
 *  paperwork uses. One of them called `toLocaleString('ru-RU')` outright, so
 *  that screen printed Russian dates to everybody.
 *
 *  Language and number format are separate choices, and this hook is where the
 *  second one lives.
 */
export function usePrefs() {
  const { i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)

  const unit = (user?.unit_weight as WeightUnit) ?? 'kg'
  const style = (user?.date_format as DateStyle) ?? 'eu'
  // T3.11.07 — the currencies new trips may start in. Chosen once in the
  // profile rather than re-picked on every publication, which is a field always
  // answered the same way. **Order is meaningful**: the first entry is what the
  // form pre-fills, the rest are the chips offered beside it.
  const currencies = user?.default_currencies?.length
    ? user.default_currencies
    : ['USD']
  const currency = currencies[0]

  return {
    unit,
    style,
    currency,
    currencies,
    /** Kilograms in, the account's unit out. Storage stays metric. */
    weight: (kg: number | null | undefined) => formatWeight(kg, unit),
    /** T3.11.07 — the same conversion without the unit suffix, for the places
     *  that put the number **into a field** rather than print it: a form input
     *  showing "50 lb" cannot be typed into. Storage stays metric either way —
     *  `toKilograms` is what goes back to the API. */
    toUnit: (kg: number) => toDisplayWeight(kg, unit),
    toKg: (value: number) => toKilograms(value, unit),
    date: (iso: string | null | undefined) => formatDate(iso, style, i18n.language),
    dateTime: (iso: string | null | undefined) =>
      formatDateTime(iso, style, i18n.language),
    time: (iso: string | null | undefined) => {
      if (!iso) return '—'
      const d = new Date(iso)
      if (Number.isNaN(d.getTime())) return '—'
      return d.toLocaleTimeString(style === 'us' ? 'en-US' : i18n.language, {
        hour: '2-digit',
        minute: '2-digit',
        hour12: style === 'us',
      })
    },
  }
}
