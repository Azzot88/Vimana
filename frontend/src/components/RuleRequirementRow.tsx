import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  deleteRequirement,
  patchRequirement,
  type DocumentRequirement,
} from '../api/rules'
import MonoText from './MonoText'

const FIELD =
  'w-full border border-navy/20 rounded-field px-3 py-1.5 text-sm font-body text-navy focus:outline-none focus:border-cyan'
const BTN = 'text-xs font-display font-medium px-3 py-1.5 rounded-field disabled:opacity-50'

/**
 * T3.11.02 pt.2 — one required document, editable in place.
 *
 * `lead_time_days` is the field worth the most attention on this row: it is what
 * the checklist counts backwards from the departure date, and it is the one
 * number a person cannot look up for themselves. A typo in it is a person who
 * ordered a paper too late and was told nothing.
 *
 * The condition is edited as JSON. The predicate has eight attributes and one
 * level of grouping; a builder for it is a screen of its own, and the API
 * answers a bad one with the reason, naming the unknown attribute. So a typo is
 * refused, not stored.
 */
export default function RuleRequirementRow({
  requirement,
  frozen,
  busy,
  run,
}: {
  requirement: DocumentRequirement
  frozen: boolean
  busy: boolean
  run: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(requirement)
  const [conditionText, setConditionText] = useState('')

  const openEdit = () => {
    setDraft(requirement)
    setConditionText(
      requirement.condition ? JSON.stringify(requirement.condition, null, 0) : '',
    )
    setEditing(true)
  }

  if (editing) {
    return (
      <div className="rounded-field border border-navy/10 p-3 space-y-2">
        <div className="flex gap-2">
          <input
            value={draft.code}
            onChange={(e) => setDraft({ ...draft, code: e.target.value })}
            placeholder={t('adminRules.reqCodePlaceholder') as string}
            className={FIELD}
          />
          <input
            value={draft.lead_time_days ?? ''}
            onChange={(e) =>
              setDraft({
                ...draft,
                lead_time_days: e.target.value ? Number(e.target.value) : null,
              })
            }
            placeholder={t('adminRules.reqLeadPlaceholder') as string}
            inputMode="numeric"
            className={FIELD}
          />
        </div>
        <input
          value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          placeholder={t('adminRules.reqTitlePlaceholder') as string}
          className={FIELD}
        />
        <input
          value={draft.issuer}
          onChange={(e) => setDraft({ ...draft, issuer: e.target.value })}
          placeholder={t('adminRules.reqIssuerPlaceholder') as string}
          className={FIELD}
        />
        <textarea
          value={conditionText}
          onChange={(e) => setConditionText(e.target.value)}
          placeholder={t('adminRules.reqConditionPlaceholder') as string}
          rows={2}
          className={`${FIELD} font-mono text-xs`}
        />
        <textarea
          value={draft.notes}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
          placeholder={t('adminRules.reqNotesPlaceholder') as string}
          rows={2}
          className={FIELD}
        />
        <div className="flex gap-2">
          <button
            onClick={() =>
              run(async () => {
                let condition: Record<string, unknown> | null = null
                if (conditionText.trim()) {
                  try {
                    condition = JSON.parse(conditionText)
                  } catch {
                    throw new Error(t('adminRules.badJson') as string)
                  }
                }
                await patchRequirement(requirement.id, {
                  code: draft.code.trim(),
                  title: draft.title.trim(),
                  issuer: draft.issuer.trim(),
                  obtained_by: draft.obtained_by,
                  lead_time_days: draft.lead_time_days,
                  valid_for_days: draft.valid_for_days,
                  condition,
                  notes: draft.notes,
                })
                setEditing(false)
              })
            }
            disabled={busy || !draft.code.trim() || !draft.title.trim()}
            className={`${BTN} bg-amber text-white hover:opacity-90`}
          >
            {t('common.save')}
          </button>
          <button
            onClick={() => setEditing(false)}
            className={`${BTN} border border-navy/20 text-navy`}
          >
            {t('common.cancel')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-field border border-navy/10 p-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <MonoText className="text-xs text-navy/70">{requirement.code}</MonoText>
        <p className="text-sm font-body text-navy">{requirement.title}</p>
        <p className="text-xs font-body text-navy/50">
          {requirement.issuer || '—'}
          {requirement.lead_time_days != null &&
            ` · ${t('adminRules.leadDays', { days: requirement.lead_time_days })}`}
        </p>
        {requirement.condition && (
          <MonoText className="text-[11px] text-navy/50">
            {JSON.stringify(requirement.condition)}
          </MonoText>
        )}
        {requirement.notes && (
          <p className="text-xs font-body text-navy/50">{requirement.notes}</p>
        )}
      </div>
      {!frozen && (
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            onClick={openEdit}
            className="text-xs font-body text-cyan hover:underline"
          >
            {t('common.edit')}
          </button>
          <button
            onClick={() => run(() => deleteRequirement(requirement.id))}
            disabled={busy}
            className="text-xs font-body text-danger hover:underline"
          >
            {t('common.delete')}
          </button>
        </div>
      )}
    </div>
  )
}
