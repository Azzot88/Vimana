import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import {
  addRequirement,
  addSection,
  changeRuleStatus,
  createRuleSet,
  deleteRuleSet,
  getRuleSet,
  listJurisdictions,
  listRuleSets,
  type Jurisdiction,
  type RuleDirection,
  type RuleSet,
  type RuleSetDetail,
  type RuleStatus,
  type StatusEvent,
  patchRuleSet,
  ruleHistory,
} from '../api/rules'
import { hasRole, isSuperuser } from '../lib/permissions'
import { usePrefs } from '../hooks/usePrefs'
import { useAuthStore } from '../stores/auth'
import MonoText from '../components/MonoText'
import RuleSectionCard from '../components/RuleSectionCard'
import RuleRequirementRow from '../components/RuleRequirementRow'

/**
 * T3.11.02 — the rules editor.
 *
 * A page in the existing admin area, by the pattern of `AdminNoticesPage` and
 * `AdminParamsPage` — not a second panel.
 *
 * Two things on this screen are load-bearing and are not styling:
 *
 * **Blockers are shown before the button is pressed.** The publication gate
 * lives on the API (`core/rule_status`) and refuses regardless of what this
 * page draws — but an editor who learns what is missing only by being refused
 * will go hunting. The list names the section that lacks a citation.
 *
 * **A published set is read-only here because it is read-only there.** The
 * screen does not decide that; it reflects it. A correction is a new version,
 * so what a reader saw stays what they saw.
 */
const DIRECTIONS: RuleDirection[] = ['export', 'import', 'transit']
const LOCALES = ['en', 'ru']

export default function AdminRulesPage() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const prefs = usePrefs()

  const [sets, setSets] = useState<RuleSet[] | null>(null)
  const [detail, setDetail] = useState<RuleSetDetail | null>(null)
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const canEdit = hasRole(user, 'compliance_editor') || isSuperuser(user)
  const canPublish = isSuperuser(user)

  if (!canEdit) return <Navigate to="/dashboard" replace />

  const frozen = detail ? detail.status === 'published' || detail.status === 'outdated' : true

  const loadList = async () => {
    try {
      const { data } = await listRuleSets()
      setSets(data)
      setError('')
    } catch {
      setSets([])
      setError(t('adminRules.loadFailed') as string)
    }
  }

  const openSet = async (id: string) => {
    try {
      const { data } = await getRuleSet(id)
      setDetail(data)
      setError('')
    } catch {
      setError(t('adminRules.loadFailed') as string)
    }
  }

  useEffect(() => {
    void loadList()
    listJurisdictions()
      .then(({ data }) => setJurisdictions(data))
      .catch(() => {})
  }, [])

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      await loadList()
      if (detail) await openSet(detail.id)
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { detail?: string } } })?.response
        ?.data?.detail
      // The API's own sentence, not a generic failure: it names the section
      // that lacks a citation, and that is the actionable part.
      setError(typeof message === 'string' ? message : t('adminRules.actionFailed'))
    } finally {
      setBusy(false)
    }
  }

  // ── create ───────────────────────────────────────────────────────────────
  const [newDirection, setNewDirection] = useState<RuleDirection>('import')
  const [newJurisdiction, setNewJurisdiction] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [newTitle, setNewTitle] = useState('')

  const create = () =>
    run(async () => {
      const { data } = await createRuleSet({
        direction: newDirection,
        jurisdiction_code: newJurisdiction,
        category_key: newCategory.trim(),
        title: newTitle.trim(),
      })
      setNewCategory('')
      setNewTitle('')
      await openSet(data.id)
    })

  // ── section / source / requirement forms ─────────────────────────────────
  const [secAnchor, setSecAnchor] = useState('')
  const [secLocale, setSecLocale] = useState('en')
  const [secTitle, setSecTitle] = useState('')
  const [secBody, setSecBody] = useState('')


  const [reqCode, setReqCode] = useState('')
  const [reqTitle, setReqTitle] = useState('')
  const [reqIssuer, setReqIssuer] = useState('')
  const [reqLead, setReqLead] = useState('')
  const [reqCondition, setReqCondition] = useState('')

  // ── set title, publication note, history ─────────────────────────────────
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  /** The "what changed" line, blog-fashion. It goes into the journal *and*
   *  onto the public page, so a reader who came back sees why the text moved
   *  rather than only that the date did. */
  const [publishNote, setPublishNote] = useState('')
  const [history, setHistory] = useState<StatusEvent[] | null>(null)

  const statusChip = (status: RuleStatus) => {
    const tone =
      status === 'published'
        ? 'bg-success/15 text-success'
        : status === 'outdated'
          ? 'bg-navy/10 text-navy/50'
          : status === 'review'
            ? 'bg-cyan/15 text-navy'
            : 'bg-amber/20 text-amber'
    return (
      <span className={`text-xs font-mono px-2 py-0.5 rounded ${tone}`}>
        {t(`adminRules.status.${status}`)}
      </span>
    )
  }

  const field =
    'w-full border border-navy/20 rounded-field px-3 py-1.5 text-sm font-body text-navy focus:outline-none focus:border-cyan'
  const btn =
    'text-xs font-display font-medium px-3 py-1.5 rounded-field disabled:opacity-50'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display font-bold text-2xl text-navy">
          {t('adminRules.title')}
        </h1>
        {/* §9b — what this is and where it lands. */}
        <p className="text-sm font-body text-navy/60 mt-1">
          {t('adminRules.description')}
        </p>
      </div>

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-[20rem_minmax(0,1fr)] gap-6 items-start">
        {/* ── list + create ───────────────────────────────────────────── */}
        <div className="space-y-4">
          <div className="bg-white rounded-card border border-navy/10 p-4 space-y-2">
            <h2 className="font-display font-semibold text-sm text-navy">
              {t('adminRules.newTitle')}
            </h2>
            <p className="text-xs font-body text-navy/50">{t('adminRules.newHint')}</p>
            <select
              value={newDirection}
              onChange={(e) => setNewDirection(e.target.value as RuleDirection)}
              aria-label={t('adminRules.direction') as string}
              className={field}
            >
              {DIRECTIONS.map((d) => (
                <option key={d} value={d}>
                  {t(`adminRules.dir.${d}`)}
                </option>
              ))}
            </select>
            <select
              value={newJurisdiction}
              onChange={(e) => setNewJurisdiction(e.target.value)}
              aria-label={t('adminRules.jurisdiction') as string}
              className={field}
            >
              <option value="">{t('adminRules.pickJurisdiction')}</option>
              {jurisdictions.map((j) => (
                <option key={j.code} value={j.code}>
                  {j.code} — {j.name}
                </option>
              ))}
            </select>
            <input
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              placeholder={t('adminRules.categoryPlaceholder') as string}
              aria-label={t('adminRules.category') as string}
              className={field}
            />
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('adminRules.titlePlaceholder') as string}
              aria-label={t('adminRules.setTitle') as string}
              className={field}
            />
            <button
              onClick={create}
              disabled={busy || !newJurisdiction || !newCategory.trim()}
              className={`${btn} bg-amber text-white hover:opacity-90 w-full`}
            >
              {t('adminRules.create')}
            </button>
          </div>

          <div className="bg-white rounded-card border border-navy/10 divide-y divide-navy/5">
            {sets === null ? (
              <p className="p-4 text-sm font-body text-navy/40">{t('common.loading')}</p>
            ) : sets.length === 0 ? (
              <p className="p-4 text-sm font-body text-navy/50">
                {t('adminRules.empty')}
              </p>
            ) : (
              sets.map((s) => (
                <button
                  key={s.id}
                  onClick={() => openSet(s.id)}
                  className={`w-full text-left p-3 hover:bg-ivory ${
                    detail?.id === s.id ? 'bg-cyan/5' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <MonoText className="text-xs text-navy/70">
                      {s.category_key} · {t(`adminRules.dir.${s.direction}`)} ·{' '}
                      {s.jurisdiction_code}
                    </MonoText>
                    {statusChip(s.status)}
                  </div>
                  <p className="text-sm font-body text-navy mt-0.5">
                    {s.title || '—'}{' '}
                    <span className="text-navy/40">v{s.version}</span>
                  </p>
                </button>
              ))
            )}
          </div>
        </div>

        {/* ── detail ──────────────────────────────────────────────────── */}
        {detail === null ? (
          <div className="bg-white rounded-card border border-navy/10 p-6">
            <p className="text-sm font-body text-navy/50">{t('adminRules.pickOne')}</p>
          </div>
        ) : (
          <div className="space-y-4 min-w-0">
            <div className="bg-white rounded-card border border-navy/10 p-5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  {editingTitle ? (
                    <div className="flex flex-wrap gap-2">
                      <input
                        value={titleDraft}
                        onChange={(e) => setTitleDraft(e.target.value)}
                        aria-label={t('adminRules.setTitle') as string}
                        className={field}
                      />
                      <button
                        onClick={() =>
                          run(async () => {
                            await patchRuleSet(detail.id, titleDraft.trim())
                            setEditingTitle(false)
                          })
                        }
                        disabled={busy}
                        className={`${btn} bg-amber text-white hover:opacity-90`}
                      >
                        {t('common.save')}
                      </button>
                      <button
                        onClick={() => setEditingTitle(false)}
                        className={`${btn} border border-navy/20 text-navy`}
                      >
                        {t('common.cancel')}
                      </button>
                    </div>
                  ) : (
                    <h2 className="font-display font-semibold text-lg text-navy">
                      {detail.title || '—'}
                      {!frozen && (
                        <button
                          onClick={() => {
                            setTitleDraft(detail.title)
                            setEditingTitle(true)
                          }}
                          className="ml-2 text-xs font-body font-normal text-cyan hover:underline"
                        >
                          {t('common.edit')}
                        </button>
                      )}
                    </h2>
                  )}
                  <MonoText className="text-xs text-navy/50">
                    {detail.category_key} · {t(`adminRules.dir.${detail.direction}`)} ·{' '}
                    {detail.jurisdiction_code} · v{detail.version}
                  </MonoText>
                </div>
                {statusChip(detail.status)}
              </div>

              {detail.reviewed_at && (
                <p className="text-xs font-body text-navy/50">
                  {t('adminRules.reviewedAt', { when: prefs.dateTime(detail.reviewed_at) })}
                </p>
              )}

              {/* Named before the attempt, and each one names its section. */}
              {detail.blockers.length > 0 && (
                <div className="rounded-field border border-amber/40 bg-amber/5 p-3 space-y-1">
                  <p className="text-xs font-display font-medium text-amber">
                    {t('adminRules.blockersTitle')}
                  </p>
                  {detail.blockers.map((b) => (
                    <p key={b} className="text-xs font-body text-navy/70">
                      {b}
                    </p>
                  ))}
                </div>
              )}

              {/* The "what changed" line, offered only where it means
                  something — at the moment of publication. Asking for it on
                  every transition would turn it into a field people skip, and
                  a skipped field is worse than an absent one: it makes the
                  ones that are filled in look optional. */}
              {detail.status === 'review' && canPublish && (
                <div className="space-y-1">
                  <label
                    htmlFor="publish-note"
                    className="block text-xs font-body text-navy/60"
                  >
                    {t('adminRules.publishNoteLabel')}
                  </label>
                  <input
                    id="publish-note"
                    value={publishNote}
                    onChange={(e) => setPublishNote(e.target.value)}
                    placeholder={t('adminRules.publishNotePlaceholder') as string}
                    className={field}
                  />
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {detail.status === 'draft' && (
                  <button
                    onClick={() => run(() => changeRuleStatus(detail.id, 'review'))}
                    disabled={busy}
                    className={`${btn} bg-navy/10 text-navy hover:bg-navy/20`}
                  >
                    {t('adminRules.toReview')}
                  </button>
                )}
                {detail.status === 'review' && (
                  <>
                    <button
                      onClick={() => run(() => changeRuleStatus(detail.id, 'draft'))}
                      disabled={busy}
                      className={`${btn} bg-navy/10 text-navy hover:bg-navy/20`}
                    >
                      {t('adminRules.backToDraft')}
                    </button>
                    {/* Absent, not disabled, when the account cannot publish:
                        a greyed button says "you may, later", and the answer
                        here is "this is somebody else's decision". */}
                    {canPublish && (
                      <button
                        onClick={() =>
                          run(async () => {
                            await changeRuleStatus(
                              detail.id,
                              'published',
                              publishNote.trim(),
                            )
                            setPublishNote('')
                          })
                        }
                        disabled={busy || detail.blockers.length > 0}
                        className={`${btn} bg-amber text-white hover:opacity-90`}
                      >
                        {t('adminRules.publish')}
                      </button>
                    )}
                  </>
                )}
                {detail.status === 'published' && canPublish && (
                  <button
                    onClick={() => run(() => changeRuleStatus(detail.id, 'outdated'))}
                    disabled={busy}
                    className={`${btn} bg-navy/10 text-navy hover:bg-navy/20`}
                  >
                    {t('adminRules.retire')}
                  </button>
                )}
                {detail.status === 'draft' && (
                  <button
                    onClick={() =>
                      run(async () => {
                        await deleteRuleSet(detail.id)
                        setDetail(null)
                      })
                    }
                    disabled={busy}
                    className={`${btn} bg-danger/10 text-danger hover:bg-danger/15`}
                  >
                    {t('adminRules.deleteDraft')}
                  </button>
                )}
              </div>

              {frozen && (
                <p className="text-xs font-body text-navy/50">
                  {t('adminRules.frozenHint')}
                </p>
              )}

              {/* T3.11.03 / T_OPS.2 — said here rather than only in the PRD.
                  The page is live for a reader the moment it is published; it
                  reaches a search engine after the next deploy, because the
                  prerender runs at build time. An editor who does not know this
                  will report it as a bug, and be right to. */}
              {detail.status === 'published' && (
                <p className="text-xs font-body text-navy/50">
                  {t('adminRules.publishDelayHint')}
                </p>
              )}

              {/* The journal, on demand rather than always. It answers "who
                  moved this and when", which is a question asked occasionally
                  and loudly — not one worth four rows of chrome on every visit. */}
              {history === null ? (
                <button
                  onClick={() =>
                    ruleHistory(detail.id)
                      .then(({ data }) => setHistory(data))
                      .catch(() => setError(t('adminRules.loadFailed') as string))
                  }
                  className="text-xs font-body text-cyan hover:underline"
                >
                  {t('adminRules.showHistory')}
                </button>
              ) : (
                <div className="rounded-field border border-navy/10 p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-display font-medium text-navy">
                      {t('adminRules.historyTitle')}
                    </p>
                    <button
                      onClick={() => setHistory(null)}
                      className="text-xs font-body text-navy/50 hover:text-navy"
                    >
                      {t('common.close')}
                    </button>
                  </div>
                  {history.map((event) => (
                    <div key={event.id} className="flex flex-wrap gap-x-2 items-baseline">
                      <MonoText className="text-[11px] text-navy/50">
                        {prefs.dateTime(event.created_at)}
                      </MonoText>
                      <span className="text-xs font-body text-navy/70">
                        {event.from_status
                          ? `${t(`adminRules.status.${event.from_status}`)} → ${t(`adminRules.status.${event.to_status}`)}`
                          : t(`adminRules.status.${event.to_status}`)}
                      </span>
                      {event.note && (
                        <span className="text-xs font-body text-navy/50">
                          — {event.note}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* ── sections ────────────────────────────────────────────── */}
            <div className="bg-white rounded-card border border-navy/10 p-5 space-y-3">
              <h3 className="font-display font-semibold text-base text-navy">
                {t('adminRules.sectionsTitle')}
              </h3>
              <p className="text-xs font-body text-navy/50">
                {t('adminRules.sectionsHint')}
              </p>

              {detail.sections.map((s, i) => (
                <RuleSectionCard
                  key={s.id}
                  section={s}
                  frozen={frozen}
                  busy={busy}
                  isFirst={i === 0}
                  isLast={i === detail.sections.length - 1}
                  run={run}
                />
              ))}

              {!frozen && (
                <div className="space-y-2 pt-2 border-t border-navy/5">
                  <div className="flex gap-2">
                    <input
                      value={secAnchor}
                      onChange={(e) => setSecAnchor(e.target.value)}
                      placeholder={t('adminRules.anchorPlaceholder') as string}
                      className={field}
                    />
                    <select
                      value={secLocale}
                      onChange={(e) => setSecLocale(e.target.value)}
                      aria-label={t('adminRules.locale') as string}
                      className={field}
                    >
                      {LOCALES.map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </div>
                  <input
                    value={secTitle}
                    onChange={(e) => setSecTitle(e.target.value)}
                    placeholder={t('adminRules.sectionTitlePlaceholder') as string}
                    className={field}
                  />
                  <textarea
                    value={secBody}
                    onChange={(e) => setSecBody(e.target.value)}
                    placeholder={t('adminRules.sectionBodyPlaceholder') as string}
                    rows={4}
                    className={field}
                  />
                  <button
                    onClick={() =>
                      run(async () => {
                        await addSection(detail.id, {
                          anchor: secAnchor.trim(),
                          locale: secLocale,
                          title: secTitle.trim(),
                          body: secBody,
                        })
                        setSecAnchor('')
                        setSecTitle('')
                        setSecBody('')
                      })
                    }
                    disabled={busy || !secAnchor.trim()}
                    className={`${btn} bg-navy/10 text-navy hover:bg-navy/20`}
                  >
                    {t('adminRules.addSection')}
                  </button>
                </div>
              )}
            </div>

            {/* ── requirements ────────────────────────────────────────── */}
            <div className="bg-white rounded-card border border-navy/10 p-5 space-y-3">
              <h3 className="font-display font-semibold text-base text-navy">
                {t('adminRules.reqTitle')}
              </h3>
              <p className="text-xs font-body text-navy/50">{t('adminRules.reqHint')}</p>

              {detail.requirements.map((r) => (
                <RuleRequirementRow
                  key={r.id}
                  requirement={r}
                  frozen={frozen}
                  busy={busy}
                  run={run}
                />
              ))}

              {!frozen && (
                <div className="space-y-2 pt-2 border-t border-navy/5">
                  <div className="flex gap-2">
                    <input
                      value={reqCode}
                      onChange={(e) => setReqCode(e.target.value)}
                      placeholder={t('adminRules.reqCodePlaceholder') as string}
                      className={field}
                    />
                    <input
                      value={reqLead}
                      onChange={(e) => setReqLead(e.target.value)}
                      placeholder={t('adminRules.reqLeadPlaceholder') as string}
                      inputMode="numeric"
                      className={field}
                    />
                  </div>
                  <input
                    value={reqTitle}
                    onChange={(e) => setReqTitle(e.target.value)}
                    placeholder={t('adminRules.reqTitlePlaceholder') as string}
                    className={field}
                  />
                  <input
                    value={reqIssuer}
                    onChange={(e) => setReqIssuer(e.target.value)}
                    placeholder={t('adminRules.reqIssuerPlaceholder') as string}
                    className={field}
                  />
                  {/* JSON by hand, deliberately: the predicate has eight
                      attributes and one level of grouping, and a builder for
                      it is a screen of its own. The API validates and answers
                      with the reason, so a typo is caught, not stored. */}
                  <textarea
                    value={reqCondition}
                    onChange={(e) => setReqCondition(e.target.value)}
                    placeholder={t('adminRules.reqConditionPlaceholder') as string}
                    rows={2}
                    className={`${field} font-mono text-xs`}
                  />
                  <button
                    onClick={() =>
                      run(async () => {
                        let condition: Record<string, unknown> | null = null
                        if (reqCondition.trim()) {
                          try {
                            condition = JSON.parse(reqCondition)
                          } catch {
                            throw new Error(t('adminRules.badJson') as string)
                          }
                        }
                        await addRequirement(detail.id, {
                          code: reqCode.trim(),
                          title: reqTitle.trim(),
                          issuer: reqIssuer.trim(),
                          lead_time_days: reqLead ? Number(reqLead) : null,
                          condition,
                        })
                        setReqCode('')
                        setReqTitle('')
                        setReqIssuer('')
                        setReqLead('')
                        setReqCondition('')
                      })
                    }
                    disabled={busy || !reqCode.trim() || !reqTitle.trim()}
                    className={`${btn} bg-navy/10 text-navy hover:bg-navy/20`}
                  >
                    {t('adminRules.addRequirement')}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
