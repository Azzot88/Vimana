import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  addSource,
  deleteSection,
  deleteSource,
  patchSection,
  patchSource,
  type RuleSection,
  type RuleSource,
} from '../api/rules'
import MonoText from './MonoText'

const FIELD =
  'w-full border border-navy/20 rounded-field px-3 py-1.5 text-sm font-body text-navy focus:outline-none focus:border-cyan'
const BTN = 'text-xs font-display font-medium px-3 py-1.5 rounded-field disabled:opacity-50'
const LOCALES = ['en', 'ru']

/**
 * T3.11.02 pt.2 — one section of a rule set, with its citations.
 *
 * The editing pattern is the one `T_UX.22` settled and `DESIGNGUIDELINES §9b`
 * records: the value is on screen, "Edit" opens a form, "Cancel" and "Save"
 * close it. A permanently open form reads as unfinished work even when nobody
 * has touched it.
 *
 * **A source is editable, not only replaceable.** Correcting a typo in an
 * authority's name used to mean deleting the citation and typing it again,
 * which loses its identity for no reason and, for a moment, leaves the section
 * uncited — the exact state the publication gate exists to catch.
 *
 * Order is moved by two buttons rather than by dragging. Dragging needs pointer
 * handling, keyboard equivalents and a scroll story to be accessible; two
 * buttons are already all three, and a corpus is reordered about twice.
 */
export default function RuleSectionCard({
  section,
  frozen,
  busy,
  isFirst,
  isLast,
  run,
}: {
  section: RuleSection
  frozen: boolean
  busy: boolean
  isFirst: boolean
  isLast: boolean
  run: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(section)
  const [addingSource, setAddingSource] = useState(false)
  const [editingSource, setEditingSource] = useState<string | null>(null)
  const [srcDraft, setSrcDraft] = useState<Partial<RuleSource>>({})

  const openEdit = () => {
    setDraft(section)
    setEditing(true)
  }

  const openSource = (source: RuleSource | null) => {
    setSrcDraft(
      source ?? { authority: '', document_title: '', url: '', quote: '' },
    )
    setEditingSource(source?.id ?? null)
    setAddingSource(source === null)
  }

  const closeSource = () => {
    setAddingSource(false)
    setEditingSource(null)
    setSrcDraft({})
  }

  const saveSource = () =>
    run(async () => {
      const payload = {
        authority: (srcDraft.authority ?? '').trim(),
        document_title: (srcDraft.document_title ?? '').trim(),
        url: (srcDraft.url ?? '').trim(),
        quote: (srcDraft.quote ?? '').trim(),
      }
      if (editingSource) await patchSource(editingSource, payload)
      else await addSource(section.id, payload)
      closeSource()
    })

  const sourceForm = (
    <div className="space-y-2 pt-1">
      <input
        value={srcDraft.authority ?? ''}
        onChange={(e) => setSrcDraft({ ...srcDraft, authority: e.target.value })}
        placeholder={t('adminRules.srcAuthority') as string}
        className={FIELD}
      />
      <input
        value={srcDraft.document_title ?? ''}
        onChange={(e) => setSrcDraft({ ...srcDraft, document_title: e.target.value })}
        placeholder={t('adminRules.srcDocument') as string}
        className={FIELD}
      />
      <input
        value={srcDraft.url ?? ''}
        onChange={(e) => setSrcDraft({ ...srcDraft, url: e.target.value })}
        placeholder={t('adminRules.srcUrl') as string}
        className={FIELD}
      />
      <textarea
        value={srcDraft.quote ?? ''}
        onChange={(e) => setSrcDraft({ ...srcDraft, quote: e.target.value })}
        placeholder={t('adminRules.srcQuote') as string}
        rows={3}
        className={FIELD}
      />
      <div className="flex gap-2">
        <button
          onClick={saveSource}
          disabled={
            busy ||
            !(srcDraft.authority ?? '').trim() ||
            !(srcDraft.document_title ?? '').trim() ||
            !(srcDraft.quote ?? '').trim()
          }
          className={`${BTN} bg-amber text-white hover:opacity-90`}
        >
          {t('common.save')}
        </button>
        <button onClick={closeSource} className={`${BTN} border border-navy/20 text-navy`}>
          {t('common.cancel')}
        </button>
      </div>
    </div>
  )

  return (
    <div className="rounded-field border border-navy/10 p-3 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <MonoText className="text-xs text-navy/70">
          {section.anchor} · {section.locale} · #{section.order}
        </MonoText>
        {!frozen && (
          <div className="flex items-center gap-3">
            {/* Order is a number, so moving is a swap with the neighbour. The
                buttons disappear at the ends rather than greying out: there is
                nothing there to move towards. */}
            {!isFirst && (
              <button
                onClick={() =>
                  run(() =>
                    patchSection(section.id, { ...section, order: section.order - 1 }),
                  )
                }
                disabled={busy}
                aria-label={t('adminRules.moveUp') as string}
                className="text-xs font-body text-navy/60 hover:text-navy"
              >
                ↑
              </button>
            )}
            {!isLast && (
              <button
                onClick={() =>
                  run(() =>
                    patchSection(section.id, { ...section, order: section.order + 1 }),
                  )
                }
                disabled={busy}
                aria-label={t('adminRules.moveDown') as string}
                className="text-xs font-body text-navy/60 hover:text-navy"
              >
                ↓
              </button>
            )}
            <button
              onClick={openEdit}
              className="text-xs font-body text-cyan hover:underline"
            >
              {t('common.edit')}
            </button>
            <button
              onClick={() => run(() => deleteSection(section.id))}
              disabled={busy}
              className="text-xs font-body text-danger hover:underline"
            >
              {t('common.delete')}
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <div className="flex gap-2">
            <input
              value={draft.anchor}
              onChange={(e) => setDraft({ ...draft, anchor: e.target.value })}
              placeholder={t('adminRules.anchorPlaceholder') as string}
              className={FIELD}
            />
            <select
              value={draft.locale}
              onChange={(e) => setDraft({ ...draft, locale: e.target.value })}
              aria-label={t('adminRules.locale') as string}
              className={FIELD}
            >
              {LOCALES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <input
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            placeholder={t('adminRules.sectionTitlePlaceholder') as string}
            className={FIELD}
          />
          <textarea
            value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })}
            placeholder={t('adminRules.sectionBodyPlaceholder') as string}
            rows={8}
            className={FIELD}
          />
          <div className="flex gap-2">
            <button
              onClick={() =>
                run(async () => {
                  await patchSection(section.id, {
                    anchor: draft.anchor.trim(),
                    locale: draft.locale,
                    order: draft.order,
                    title: draft.title.trim(),
                    body: draft.body,
                  })
                  setEditing(false)
                })
              }
              disabled={busy || !draft.anchor.trim()}
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
      ) : (
        <>
          <p className="text-sm font-body text-navy">{section.title || '—'}</p>
          <p className="text-xs font-body text-navy/60 whitespace-pre-wrap">
            {section.body}
          </p>
        </>
      )}

      {section.sources.length === 0 ? (
        <p className="text-xs font-mono text-amber">{t('adminRules.noSource')}</p>
      ) : (
        section.sources.map((src) =>
          editingSource === src.id ? (
            <div key={src.id}>{sourceForm}</div>
          ) : (
            <div key={src.id} className="rounded-field bg-ivory p-2 space-y-0.5">
              <MonoText className="text-[11px] text-navy/60">
                {src.authority} · {src.document_title}
              </MonoText>
              <p className="text-xs font-body text-navy/70 italic">«{src.quote}»</p>
              {!frozen && (
                <div className="flex gap-3">
                  <button
                    onClick={() => openSource(src)}
                    className="text-[11px] font-body text-cyan hover:underline"
                  >
                    {t('common.edit')}
                  </button>
                  <button
                    onClick={() => run(() => deleteSource(src.id))}
                    disabled={busy}
                    className="text-[11px] font-body text-danger hover:underline"
                  >
                    {t('common.delete')}
                  </button>
                </div>
              )}
            </div>
          ),
        )
      )}

      {!frozen &&
        (addingSource ? (
          sourceForm
        ) : (
          <button
            onClick={() => openSource(null)}
            className="text-xs font-body text-cyan hover:underline"
          >
            {t('adminRules.addSource')}
          </button>
        ))}
    </div>
  )
}
