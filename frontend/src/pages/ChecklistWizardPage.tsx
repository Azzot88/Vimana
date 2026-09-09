import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import {
  buildChecklist,
  saveCase,
  type Checklist,
  type ChecklistItem,
} from '../api/checklist'
import { rulesIndex, type RuleIndexEntry } from '../api/rulesPublic'
import DateTimeField from '../components/DateTimeField'
import MonoText from '../components/MonoText'
import { usePrefs } from '../hooks/usePrefs'

/** T3.11.06 — «что мне нужно собрать, и не поздно ли уже».
 *
 *  **No account, by design.** `MASTERPLAN §4.1` makes the corpus free for the
 *  same reason matching is free: text is copyable, and text nobody can read
 *  without an account is text nobody reads. A sign-up wall here would be a
 *  sign-up form pretending to be a service.
 *
 *  **The corridor is picked from what the corpus actually covers.** Two empty
 *  fields asking for jurisdiction codes would be a form that only its author can
 *  fill in; the published index already says which corridors are answered, so
 *  the wizard offers those and says plainly that the rest are not written yet.
 *
 *  **The questionnaire is not a fixed list.** The server returns `asks` —
 *  computed from the conditions in the corpus — so a rule that grows a clause
 *  grows this form with it, and nobody has to remember to add a field.
 *
 *  **The red line is the point.** The median horizon on this market is five days
 *  and 31 % of trips are published inside two, so «не успеваете» is not an edge
 *  case: it is what a third of readers need to see first, and it is the only
 *  thing on this screen drawn in the danger colour.
 *
 *  Functions (PROJECT §6.2a):
 *  - `ChecklistWizardPage()` — default export. Called by: `App` at `/checklist`.
 */
export default function ChecklistWizardPage() {
  const { t, i18n } = useTranslation()
  const prefs = usePrefs()
  const [params, setParams] = useSearchParams()

  const [index, setIndex] = useState<RuleIndexEntry[]>([])
  const [category, setCategory] = useState(params.get('category') ?? '')
  const [origin, setOrigin] = useState(params.get('origin') ?? '')
  const [destination, setDestination] = useState(params.get('destination') ?? '')
  const [departAt, setDepartAt] = useState('')
  const [attrs, setAttrs] = useState<Record<string, unknown>>({})
  // What was typed, kept beside what was sent: the input has to show «50»
  // while the request carries `50`, and re-deriving one from the other would
  // turn a half-typed «-» into a zero under the cursor.
  const [raw, setRaw] = useState<Record<string, string>>({})
  const [result, setResult] = useState<Checklist | null>(null)
  const [busy, setBusy] = useState(false)
  const [savedId, setSavedId] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    rulesIndex(i18n.language)
      .then(({ data }) => setIndex(data))
      .catch(() => setIndex([]))
  }, [i18n.language])

  /* What the corpus can answer, derived from the index rather than kept as a
     second list: a hand-written one would offer a corridor the day before it
     was written and keep offering it the day after it was withdrawn. */
  const categories = useMemo(
    () => [...new Set(index.map((e) => e.category_key))].sort(),
    [index],
  )
  const placesFor = (direction: 'export' | 'import') =>
    [
      ...new Set(
        index
          .filter((e) => e.category_key === category && e.direction === direction)
          .map((e) => e.jurisdiction_code),
      ),
    ].sort()

  const origins = useMemo(() => placesFor('export'), [index, category])
  const destinations = useMemo(() => placesFor('import'), [index, category])

  const build = async () => {
    if (!origin || !destination || !category) return
    setBusy(true)
    setError('')
    try {
      const { data } = await buildChecklist({
        origin,
        destination,
        category,
        attrs,
        depart_at: departAt ? departAt.slice(0, 10) : null,
      })
      setResult(data)
      // In the address, so a corridor somebody worked out can be sent to the
      // person who actually has to collect the documents.
      setParams({ category, origin, destination }, { replace: true })
    } catch {
      setError(t('checklist.buildFailed'))
    } finally {
      setBusy(false)
    }
  }

  const keep = async () => {
    setBusy(true)
    setError('')
    try {
      const { data } = await saveCase({
        origin,
        destination,
        category,
        attrs,
        depart_at: departAt ? departAt.slice(0, 10) : null,
      })
      setSavedId(data.id)
    } catch {
      setError(t('checklist.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  /* Typed as text, sent as what the corpus compares. `age_years >= 50` is a
     numeric comparison and the evaluator refuses a string there, so «50» must
     not travel as `"50"`. */
  const answer = (attr: string, value: string) => {
    setRaw((prev) => ({ ...prev, [attr]: value }))
    setAttrs((prev) => ({ ...prev, [attr]: coerce(value) }))
  }

  const row = (item: ChecklistItem) => (
    <li
      key={`${item.jurisdiction_code}-${item.code}`}
      className={`rounded-card border p-4 space-y-1 ${
        item.too_late
          ? 'border-danger/40 bg-danger/5'
          : 'border-navy/10 bg-white'
      }`}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <span className="font-display font-semibold text-sm text-navy">
          {item.title}
        </span>
        <span className="text-[10px] font-mono uppercase text-navy/40">
          {item.jurisdiction_code} · {t(`rulesPage.dir.${item.direction}`, item.direction)}
        </span>
      </div>
      {item.issuer && (
        <p className="text-xs font-body text-navy/50">{item.issuer}</p>
      )}
      <div className="flex flex-wrap gap-3 text-xs font-body">
        {/* «Уточните» rather than «обязательно»: the document is in the list
            because an answer is missing, and calling that a requirement would
            state something the corpus has not said. */}
        {item.undecided ? (
          <span className="text-amber">{t('checklist.undecided')}</span>
        ) : item.is_mandatory ? (
          <span className="text-navy/70">{t('checklist.mandatory')}</span>
        ) : (
          <span className="text-navy/40">{t('checklist.optional')}</span>
        )}
        {item.lead_time_days != null && (
          <span className="text-navy/50">
            {t('checklist.leadTime', { count: item.lead_time_days })}
          </span>
        )}
        {item.valid_for_days != null && (
          <span className="text-navy/50">
            {t('checklist.validFor', { count: item.valid_for_days })}
          </span>
        )}
      </div>
      {item.start_by && (
        <p
          className={`text-xs font-body ${
            item.too_late ? 'text-danger font-medium' : 'text-navy/50'
          }`}
        >
          {item.too_late
            ? t('checklist.tooLate', { date: prefs.date(item.start_by) })
            : t('checklist.startBy', { date: prefs.date(item.start_by) })}
        </p>
      )}
    </li>
  )

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="font-display font-semibold text-2xl text-navy">
          {t('checklist.title')}
        </h1>
        {/* DESIGNGUIDELINES §9b — what this screen does and what it does not. */}
        <p className="text-sm font-body text-navy/60 mt-1">
          {t('checklist.lead')}
        </p>
      </div>

      <section className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
        <label className="block">
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('checklist.category')}
          </span>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value)
              setOrigin('')
              setDestination('')
              setResult(null)
            }}
            className="w-full px-3 py-2 rounded-field border border-navy/15 font-body text-sm"
          >
            <option value="">—</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {t(`categories.${c}`, { defaultValue: c })}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-wrap gap-3">
          <label className="flex-1 min-w-[9rem]">
            <span className="block text-xs font-body text-navy/40 mb-1">
              {t('checklist.from')}
            </span>
            <select
              value={origin}
              disabled={!category}
              onChange={(e) => setOrigin(e.target.value)}
              className="w-full px-3 py-2 rounded-field border border-navy/15 font-body text-sm disabled:bg-navy/5"
            >
              <option value="">—</option>
              {origins.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="flex-1 min-w-[9rem]">
            <span className="block text-xs font-body text-navy/40 mb-1">
              {t('checklist.to')}
            </span>
            <select
              value={destination}
              disabled={!category}
              onChange={(e) => setDestination(e.target.value)}
              className="w-full px-3 py-2 rounded-field border border-navy/15 font-body text-sm disabled:bg-navy/5"
            >
              <option value="">—</option>
              {destinations.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Optional, and the screen says what leaving it empty costs rather than
            demanding it: a person who has not chosen a flight still deserves the
            list, they just do not get the deadlines. */}
        <div>
          <span className="block text-xs font-body text-navy/40 mb-1">
            {t('checklist.departAt')}
          </span>
          <DateTimeField value={departAt} onChange={setDepartAt} style={prefs.style} />
          <p className="text-[11px] font-body text-navy/40 mt-1">
            {t('checklist.departHint')}
          </p>
        </div>

        {category && origin && destination && (
          <button
            type="button"
            onClick={build}
            disabled={busy}
            className="bg-navy text-ivory font-display font-medium text-sm px-4 py-2 min-h-[2.75rem] rounded-field hover:bg-navy-mid disabled:opacity-50"
          >
            {busy ? t('common.loading') : t('checklist.build')}
          </button>
        )}
        {categories.length === 0 && (
          <p className="text-xs font-body text-navy/40">
            {t('checklist.noCorpus')}
          </p>
        )}
      </section>

      {/* The questionnaire, built from what the corpus asks. Shown after the
          first build rather than before it: the questions depend on the
          corridor, and asking them up front would ask about rules that do not
          apply here. */}
      {result && result.asks.length > 0 && (
        <section className="bg-white rounded-card border border-navy/10 p-4 space-y-3">
          <h2 className="font-display font-semibold text-sm text-navy">
            {t('checklist.questions')}
          </h2>
          <p className="text-[11px] font-body text-navy/40">
            {t('checklist.questionsHint')}
          </p>
          <div className="flex flex-wrap gap-3">
            {result.asks.map((attr) => (
              <label key={attr} className="flex-1 min-w-[10rem]">
                <span className="block text-xs font-body text-navy/40 mb-1">
                  {t(`checklist.attr.${attr}`, { defaultValue: attr })}
                </span>
                <input
                  value={raw[attr] ?? ''}
                  onChange={(e) => answer(attr, e.target.value)}
                  placeholder={
                    t(`checklist.attrHint.${attr}`, { defaultValue: '' }) as string
                  }
                  className="w-full px-3 py-2 rounded-field border border-navy/15 font-body text-sm"
                />
              </label>
            ))}
          </div>
          <button
            type="button"
            onClick={build}
            disabled={busy}
            className="border border-navy/20 text-navy font-body text-sm px-4 py-2 min-h-[2.75rem] rounded-field hover:bg-navy/5 disabled:opacity-50"
          >
            {t('checklist.rebuild')}
          </button>
        </section>
      )}

      {error && <p className="text-xs font-mono text-danger">{error}</p>}

      {result && (
        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <h2 className="font-display font-semibold text-lg text-navy">
              {t('checklist.result', { count: result.items.length })}
            </h2>
            {result.corridor.length > 0 && (
              <MonoText className="text-xs text-navy/40">
                {result.corridor.join(' → ')}
              </MonoText>
            )}
          </div>

          {result.items.length === 0 ? (
            <p className="text-sm font-body text-navy/50">
              {t('checklist.empty')}
            </p>
          ) : (
            <ul className="space-y-2">{result.items.map(row)}</ul>
          )}

          {result.items.length > 0 && (
            <div className="space-y-2 pt-2">
              {savedId ? (
                <p className="text-xs font-body text-navy/60">
                  {t('checklist.saved')}{' '}
                  <MonoText className="text-xs text-navy">{savedId}</MonoText>
                </p>
              ) : (

                <button
                  type="button"
                  onClick={keep}
                  disabled={busy}
                  className="border border-cyan/40 text-cyan font-body text-sm px-4 py-2 min-h-[2.75rem] rounded-field hover:bg-cyan/10 disabled:opacity-50"
                >
                  {t('checklist.keep')}
                </button>
              )}
              {/* §9.1 — what this is and what it is not, in the same place as
                  the list. The platform collects published requirements; it does
                  not rule on anybody's paperwork. */}
              <p className="text-[11px] font-body text-navy/40">
                {t('checklist.disclaimer')}
              </p>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

/** Numbers arrive as numbers and everything else as text.
 *
 *  The corpus compares `age_years >= 50` numerically, and a string there is
 *  refused by the evaluator — so a person typing «50» must not send `"50"`.
 *  Booleans are the same story in the other direction: `author_known` is
 *  answered yes or no, and «yes» is not a boolean. */
function coerce(value: string): unknown {
  const trimmed = value.trim()
  if (trimmed === '') return ''
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed)
  const lower = trimmed.toLowerCase()
  if (lower === 'true' || lower === 'yes' || lower === 'да') return true
  if (lower === 'false' || lower === 'no' || lower === 'нет') return false
  return trimmed
}
