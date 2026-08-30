import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { deleteQuestion, patchQuestion, type RuleQuestion } from '../api/rules'
import MonoText from './MonoText'

const FIELD =
  'w-full border border-navy/20 rounded-field px-3 py-1.5 text-sm font-body text-navy focus:outline-none focus:border-cyan'
const BTN = 'text-xs font-display font-medium px-3 py-1.5 rounded-field disabled:opacity-50'

/**
 * T3.11.05 — one question and its short answer, editable in place.
 *
 * The field that carries the design is `section_anchor`. It is edited as a
 * **select over the set's own section anchors**, not as free text: an anchor
 * typed by hand is a question that looks finished, saves without complaint, and
 * blocks publication later with a message the editor has to decode. A list of
 * what exists cannot be mistyped.
 *
 * The row still says so when a stored anchor no longer resolves — a section can
 * be renamed or deleted after the question was written, and the select would
 * otherwise quietly show the first option as though nothing were wrong.
 */
export default function RuleQuestionRow({
  question,
  sectionAnchors,
  frozen,
  busy,
  run,
}: {
  question: RuleQuestion
  /** Anchors present in this set — the whole list, in section order. */
  sectionAnchors: string[]
  frozen: boolean
  busy: boolean
  run: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(question)

  const resolves = sectionAnchors.includes(question.section_anchor)

  if (editing) {
    return (
      <div className="rounded-field border border-navy/10 p-3 space-y-2">
        <div className="flex gap-2">
          <input
            value={draft.anchor}
            onChange={(e) => setDraft({ ...draft, anchor: e.target.value })}
            placeholder={t('adminRules.questionAnchor') as string}
            className={`${FIELD} font-mono text-xs`}
          />
          <input
            value={draft.locale}
            onChange={(e) => setDraft({ ...draft, locale: e.target.value })}
            className={`${FIELD} font-mono text-xs w-24`}
          />
        </div>
        <input
          value={draft.question}
          onChange={(e) => setDraft({ ...draft, question: e.target.value })}
          placeholder={t('adminRules.questionLabel') as string}
          className={FIELD}
        />
        <textarea
          value={draft.answer}
          onChange={(e) => setDraft({ ...draft, answer: e.target.value })}
          placeholder={t('adminRules.answerLabel') as string}
          rows={4}
          className={FIELD}
        />
        <label className="block space-y-1">
          <span className="text-xs font-body text-navy/60">
            {t('adminRules.answersFrom')}
          </span>
          <select
            value={draft.section_anchor}
            onChange={(e) => setDraft({ ...draft, section_anchor: e.target.value })}
            className={`${FIELD} font-mono text-xs`}
          >
            {/* The stored value stays selectable even when it no longer
                resolves. Dropping it would silently rewrite the question to
                point somewhere else the moment somebody opened the editor. */}
            {!sectionAnchors.includes(draft.section_anchor) && (
              <option value={draft.section_anchor}>
                {draft.section_anchor} — {t('adminRules.answersFromMissing')}
              </option>
            )}
            {sectionAnchors.map((anchor) => (
              <option key={anchor} value={anchor}>
                {anchor}
              </option>
            ))}
          </select>
        </label>
        <div className="flex gap-2">
          <button
            onClick={() =>
              run(async () => {
                await patchQuestion(question.id, {
                  anchor: draft.anchor.trim(),
                  locale: draft.locale.trim(),
                  order: draft.order,
                  question: draft.question.trim(),
                  answer: draft.answer,
                  section_anchor: draft.section_anchor.trim(),
                })
                setEditing(false)
              })
            }
            disabled={
              busy ||
              !draft.anchor.trim() ||
              !draft.question.trim() ||
              !draft.section_anchor.trim()
            }
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
      <div className="min-w-0 space-y-1">
        <MonoText className="text-[11px] text-navy/50">
          {question.anchor} · {question.locale}
        </MonoText>
        <p className="text-sm font-body text-navy">{question.question}</p>
        <p className="text-xs font-body text-navy/60 whitespace-pre-wrap">
          {question.answer}
        </p>
        {/* Named on the row, not only in the editor: this is what a reviewer
            checks, and it is the field that decides whether the set publishes. */}
        <MonoText
          className={`text-[11px] ${resolves ? 'text-navy/50' : 'text-danger'}`}
        >
          {t('adminRules.answersFrom')}: {question.section_anchor}
          {!resolves && ` — ${t('adminRules.answersFromMissing')}`}
        </MonoText>
      </div>
      {!frozen && (
        <div className="flex shrink-0 flex-col items-end gap-1">
          <button
            onClick={() => {
              setDraft(question)
              setEditing(true)
            }}
            className="text-xs font-body text-cyan hover:underline"
          >
            {t('common.edit')}
          </button>
          <button
            onClick={() => run(() => deleteQuestion(question.id))}
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
