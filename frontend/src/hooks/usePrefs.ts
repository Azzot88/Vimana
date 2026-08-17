import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import {
  formatDate,
  formatDateTime,
  formatWeight,
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

  return {
    unit,
    style,
    /** Kilograms in, the account's unit out. Storage stays metric. */
    weight: (kg: number | null | undefined) => formatWeight(kg, unit),
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
