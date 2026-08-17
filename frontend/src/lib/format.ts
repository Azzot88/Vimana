/** T_UX.14 — printing weights and dates the way this account reads them.
 *
 *  Stored on the user rather than read from the browser: a carrier flying
 *  between metric and imperial countries thinks in one of them, and that does
 *  not change with the device they happen to open the site on.
 *
 *  Weight converts, dates only reformat. A kilogram shown in pounds is the same
 *  weight; a date shown American-style is the same instant. Nothing here
 *  changes what was agreed — the contract stores kilograms and ISO timestamps,
 *  and these functions are display only.
 */
export type WeightUnit = 'kg' | 'lb'
export type DateStyle = 'eu' | 'us'

const LB_PER_KG = 2.20462

export function toDisplayWeight(kg: number, unit: WeightUnit): number {
  return unit === 'lb' ? kg * LB_PER_KG : kg
}

export function toKilograms(value: number, unit: WeightUnit): number {
  return unit === 'lb' ? value / LB_PER_KG : value
}

export function formatWeight(kg: number | null | undefined, unit: WeightUnit): string {
  if (kg === null || kg === undefined || Number.isNaN(kg)) return '—'
  const v = toDisplayWeight(kg, unit)
  // Two decimals only when the conversion produced them: "5 kg" reads better
  // than "5.00 kg", and "11.02 lb" must not become "11 lb".
  const printed = Number.isInteger(v) ? String(v) : v.toFixed(2)
  return `${printed} ${unit}`
}

export function formatDateTime(
  iso: string | null | undefined,
  style: DateStyle,
  locale?: string,
): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  // `hour12` is the actual difference people notice; the day/month order
  // follows from the locale tag, which is why the two travel as one setting.
  return d.toLocaleString(style === 'us' ? 'en-US' : locale || 'en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: style === 'us',
  })
}

export function formatDate(
  iso: string | null | undefined,
  style: DateStyle,
  locale?: string,
): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(style === 'us' ? 'en-US' : locale || 'en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}
