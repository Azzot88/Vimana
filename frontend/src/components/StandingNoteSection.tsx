import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { updateMe, type UserUpdate } from '../api/auth'
import { useAuthStore } from '../stores/auth'

export type NoteFieldName =
  | 'carriage_rules'
  | 'interaction_rules'
  | 'payment_instructions'

export interface NoteField {
  name: NoteFieldName
  labelKey: string
  /** The line under the label. Required, not optional — see the note below. */
  descKey: string
  placeholderKey?: string
  rows?: number
}

interface Props {
  titleKey: string
  descKey: string
  fields: NoteField[]
}

/**
 * T_UX.22 — a standing note in the same shape as everything else in the
 * profile: read it, press «Изменить», edit, save. «Добавить» while it is empty.
 *
 * The permanently open textarea it replaces was the odd one out on the screen —
 * the postal addresses next to it have always worked this way — and an open
 * field reads as unsaved work even when nothing has been touched.
 *
 * **Every heading carries a line of description** (owner's rule, 2026-08-23,
 * written into DESIGNGUIDELINES §9b). Hence `descKey` is required rather than
 * optional: a setting whose effect is not stated is one people either leave
 * alone or discover by accident, and an optional field is one that quietly goes
 * unfilled.
 *
 * One component takes a list of fields because two of them belong on one card:
 * the carriage rules and how the carrier works are one section to the reader,
 * while staying two columns with different behaviour underneath — the carriage
 * rules are copied into each trip (T_UX.15), the working notes are not.
 */
export default function StandingNoteSection({ titleKey, descKey, fields }: Props) {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)

  const current = (name: NoteFieldName) => user?.[name] ?? ''
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const groupId = useId()

  const filled = fields.some((f) => current(f.name).trim().length > 0)

  const openEditor = () => {
    setDraft(Object.fromEntries(fields.map((f) => [f.name, current(f.name)])))
    setError('')
    setEditing(true)
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      // The whole card in one request: both boxes were open together, so
      // sending them together is what the person just did. Untouched fields go
      // back unchanged rather than being omitted — the draft was seeded from
      // the stored values, so there is nothing to lose.
      const patch = Object.fromEntries(
        fields.map((f) => [f.name, draft[f.name] ?? '']),
      ) as UserUpdate
      const { data } = await updateMe(patch)
      if (token) setAuth(data, token)
      setEditing(false)
    } catch {
      setError(t('prefs.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="bg-white rounded-card border border-navy/10 p-6 space-y-4 h-full">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display font-semibold text-base text-navy">{t(titleKey)}</h2>
          <p className="text-xs font-body text-navy/50 mt-0.5">{t(descKey)}</p>
        </div>
        {!editing && (
          <button
            type="button"
            onClick={openEditor}
            className="text-xs font-body text-cyan hover:underline shrink-0"
          >
            {filled ? t('common.edit') : `+ ${t('common.add')}`}
          </button>
        )}
      </div>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {editing ? (
        <div className="space-y-4">
          {fields.map((f) => (
            <div key={f.name}>
              <label
                htmlFor={`${groupId}-${f.name}`}
                className="block text-sm font-body font-medium text-navy"
              >
                {t(f.labelKey)}
              </label>
              <p className="text-xs font-body text-navy/50 mt-0.5 mb-1.5">{t(f.descKey)}</p>
              <textarea
                id={`${groupId}-${f.name}`}
                value={draft[f.name] ?? ''}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, [f.name]: e.target.value }))
                }
                rows={f.rows ?? 4}
                maxLength={4000}
                placeholder={f.placeholderKey ? (t(f.placeholderKey) as string) : undefined}
                className="w-full border border-navy/20 rounded-field px-3 py-2 text-sm font-body text-navy focus:outline-none focus:border-cyan"
              />
            </div>
          ))}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="text-xs font-body text-navy/50 px-3 py-1.5"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => void save()}
              className="px-4 py-1.5 rounded-field bg-navy text-white text-xs font-body disabled:opacity-50"
            >
              {saving ? '…' : t('common.save')}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {fields.map((f) => {
            const value = current(f.name)
            return (
              <div key={f.name}>
                {fields.length > 1 && (
                  <p className="text-xs font-display font-semibold text-navy/50 uppercase tracking-wide">
                    {t(f.labelKey)}
                  </p>
                )}
                {value ? (
                  /* `whitespace-pre-wrap` because these are written as lists as
                     often as prose, and a rule per line is the shape people
                     type. Collapsing them into a paragraph would rewrite what
                     the carrier wrote. */
                  <p className="text-sm font-body text-navy whitespace-pre-wrap break-words mt-0.5">
                    {value}
                  </p>
                ) : (
                  <p className="text-sm font-body text-navy/40 mt-0.5">
                    {t('common.notSet')}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
