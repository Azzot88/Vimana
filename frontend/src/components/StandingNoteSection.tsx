import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { updateMe, type UserUpdate } from '../api/auth'
import { useAuthStore } from '../stores/auth'

type NoteField = 'carriage_rules' | 'interaction_rules' | 'payment_instructions'

interface Props {
  field: NoteField
  titleKey: string
  hintKey: string
  /** Placeholder is optional: two of the three read better with an example in
   *  the box, and the carriage rules already had none. */
  placeholderKey?: string
  rows?: number
}

/**
 * T_UX.21 — one component for the three standing notes a carrier writes once.
 *
 * There were about to be three copies of the same textarea, save button and
 * saved/failed pair, and DESIGNGUIDELINES §9a says the third instance is where
 * a component gets extracted: two identical blocks live peacefully, three
 * drift. They already had started to — the carriage rules box came with its own
 * label markup inside `DisplayPrefsSection`.
 *
 * The 4000-character ceiling is the server's (`UserUpdate`), repeated here as
 * `maxLength` so the limit is met while typing rather than as a 422 after the
 * text is written.
 */
export default function StandingNoteSection({
  field,
  titleKey,
  hintKey,
  placeholderKey,
  rows = 5,
}: Props) {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)

  const [value, setValue] = useState(user?.[field] ?? '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const fieldId = useId()

  const save = async () => {
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      // One field per request, so saving the answer time cannot touch the
      // payment details; the backend applies `exclude_unset`, and a test holds
      // that it keeps doing so.
      const { data } = await updateMe({ [field]: value } as UserUpdate)
      if (token) setAuth(data, token)
      setSaved(true)
    } catch {
      setError(t('prefs.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="bg-white rounded-card border border-navy/10 p-6 space-y-3">
      <div>
        <h2 className="font-display font-semibold text-base text-navy">{t(titleKey)}</h2>
        <p className="text-xs font-body text-navy/50 mt-0.5">{t(hintKey)}</p>
      </div>

      <label htmlFor={fieldId} className="sr-only">
        {t(titleKey)}
      </label>
      <textarea
        id={fieldId}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={rows}
        maxLength={4000}
        placeholder={placeholderKey ? (t(placeholderKey) as string) : undefined}
        className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={() => void save()}
          className="px-4 py-2 rounded-field bg-navy text-white text-sm font-body disabled:opacity-50"
        >
          {saving ? '…' : t('prefs.save')}
        </button>
        {error && <p className="text-xs font-body text-danger">{error}</p>}
        {saved && !error && (
          <p className="text-xs font-body text-success">{t('prefs.saved')}</p>
        )}
      </div>
    </section>
  )
}
