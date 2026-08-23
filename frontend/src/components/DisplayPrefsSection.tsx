import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { updateMe } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { formatDateTime, formatWeight, type DateStyle, type WeightUnit } from '../lib/format'

/** T_UX.14 — units and date style, and since T_UX.21 nothing else.
 *
 *  The carriage rules used to sit here too, which put the carrier's standing
 *  terms — a thing they send to clients — in the same box as the clock format.
 *  They moved to «Мои правила» with the rest of the operational text.
 *
 *  The preview under the switches is not decoration. "European" and "American"
 *  mean nothing until you see `17.08.2026, 14:30` next to `08/17/2026, 02:30 PM`
 *  — the label describes a convention, the sample describes what will actually
 *  be on the screen.
 */
export default function DisplayPrefsSection() {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)

  const [unit, setUnit] = useState<WeightUnit>((user?.unit_weight as WeightUnit) ?? 'kg')
  const [style, setStyle] = useState<DateStyle>((user?.date_format as DateStyle) ?? 'eu')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  const save = async (patch: Record<string, unknown>) => {
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const { data } = await updateMe(patch)
      if (token) setAuth(data, token)
      setSaved(true)
    } catch {
      setError(t('prefs.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const pick = <T extends string>(
    current: T,
    value: T,
    label: string,
    onPick: (v: T) => void,
  ) => (
    <button
      type="button"
      onClick={() => onPick(value)}
      /* T_UX.21 — these switches were the only writers left once the rules
         textarea moved out, and they save on click. Locking them for the
         round-trip stops a double tap from racing two PATCHes whose order
         decides the stored value. */
      disabled={saving}
      className={`px-3 py-1.5 rounded-full text-xs font-body border disabled:opacity-60 ${
        current === value
          ? 'border-cyan text-cyan bg-cyan/5'
          : 'border-navy/15 text-navy/60'
      }`}
    >
      {label}
    </button>
  )

  const sample = new Date().toISOString()

  return (
    <section className="bg-white rounded-card border border-navy/10 p-4 space-y-4">
      <div>
        <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
          {t('prefs.title')}
        </p>
        <p className="text-[11px] font-body text-navy/40 mt-0.5">{t('prefs.hint')}</p>
      </div>

      <div>
        <p className="text-[11px] font-body text-navy/40 mb-1.5">{t('prefs.weight')}</p>
        <div className="flex gap-2">
          {pick(unit, 'kg' as WeightUnit, t('prefs.kg'), (v) => {
            setUnit(v)
            void save({ unit_weight: v })
          })}
          {pick(unit, 'lb' as WeightUnit, t('prefs.lb'), (v) => {
            setUnit(v)
            void save({ unit_weight: v })
          })}
        </div>
        <p className="mt-1.5 text-[11px] font-mono text-navy/40">
          {t('prefs.example')}: {formatWeight(5, unit)}
        </p>
      </div>

      <div>
        <p className="text-[11px] font-body text-navy/40 mb-1.5">{t('prefs.dates')}</p>
        <div className="flex gap-2">
          {pick(style, 'eu' as DateStyle, t('prefs.european'), (v) => {
            setStyle(v)
            void save({ date_format: v })
          })}
          {pick(style, 'us' as DateStyle, t('prefs.american'), (v) => {
            setStyle(v)
            void save({ date_format: v })
          })}
        </div>
        <p className="mt-1.5 text-[11px] font-mono text-navy/40">
          {t('prefs.example')}: {formatDateTime(sample, style, i18n.language)}
        </p>
      </div>

      {error && <p className="text-xs font-body text-danger">{error}</p>}
      {saved && !error && (
        <p className="text-xs font-body text-success">{t('prefs.saved')}</p>
      )}
    </section>
  )
}
