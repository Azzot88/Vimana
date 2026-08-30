import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { rulesIndex, type RuleIndexEntry } from '../api/rulesPublic'
import { usePrefs } from '../hooks/usePrefs'
import LandingShell from '../components/landing/LandingShell'
import MonoText from '../components/MonoText'

/**
 * T3.11.03 pt.2 / T3.11.05 — the way in, and the controls over it.
 *
 * The corridor pages existed before this one and were reachable only by typing
 * their exact address: a directory built as the top of the funnel that nothing
 * pointed at.
 *
 * **Chronological by default** (owner's decision 2026-08-29). A rule that
 * changed last week is news; the same rule six months untouched is reference.
 * The default order answers "what moved", and that is what a returning reader
 * comes back for. Grouping by category is the other question — "where do I
 * look" — and it is one click away rather than the front door.
 *
 * The order itself comes from the API, not from a sort here: grouping is a
 * `reduce` over any list, but ordering by publication needs the dates to be
 * right, and the server is where they are.
 *
 * **The filters are built from the data, never from a list in this file.**
 * A hard-coded `['US','RU']` is correct on the day it is written and wrong on
 * the day somebody publishes a third corridor — and wrong silently, because a
 * missing chip looks exactly like a corridor that does not exist. Deriving them
 * costs one `reduce` and cannot drift.
 *
 * Filtering is client-side on purpose. The whole index is one small array that
 * the page has already fetched; a round trip per chip would make the controls
 * feel worse and answer no question the client cannot answer itself. When the
 * corpus count crosses the threshold in `T_OPS.2`, this moves with it.
 */
type Sort = 'chronological' | 'category'

/** One filter dimension: what to read off an entry, and how to label a value. */
type Facet = {
  key: 'category_key' | 'direction' | 'jurisdiction_code'
  label: (value: string, entries: RuleIndexEntry[]) => string
}

export default function RulesIndexPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [entries, setEntries] = useState<RuleIndexEntry[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [sort, setSort] = useState<Sort>('chronological')
  //: `null` means "no filter on this dimension" — distinct from a value that
  //: happens to match everything, and it is what the "all" chip restores.
  const [picked, setPicked] = useState<Record<string, string | null>>({
    category_key: null,
    direction: null,
    jurisdiction_code: null,
  })

  useEffect(() => {
    rulesIndex()
      .then(({ data }) => setEntries(data))
      .catch(() => {
        // Not silently empty: "nothing published yet" and "the request died"
        // look identical on screen, and the second reads as the first.
        setEntries([])
        setFailed(true)
      })
  }, [])

  const facets: Facet[] = useMemo(
    () => [
      {
        key: 'category_key',
        label: (v) => t(`categories.${v}`, { defaultValue: v }),
      },
      {
        key: 'direction',
        label: (v) => t(`rulesPage.dir.${v}`, { defaultValue: v }),
      },
      {
        key: 'jurisdiction_code',
        // The country's own name, taken from the entry rather than from a map
        // in this file: the API already knows it, and a second copy is a second
        // place to forget a country.
        label: (v, rows) =>
          rows.find((r) => r.jurisdiction_code === v)?.jurisdiction_name || v,
      },
    ],
    [t],
  )

  const shown = useMemo(() => {
    if (!entries) return []
    return entries.filter((entry) =>
      facets.every((f) => picked[f.key] == null || entry[f.key] === picked[f.key]),
    )
  }, [entries, picked, facets])

  /** Values of one dimension that are still reachable given the other picks.
   *
   *  Cross-filtered on purpose: offering "export" when the only export corpus
   *  is Russian and the reader has picked the US would be offering a chip that
   *  empties the page. A control that can only produce nothing is worse than an
   *  absent one, because pressing it reads as "there is nothing here".
   */
  const optionsFor = (facet: Facet): string[] => {
    if (!entries) return []
    const others = facets.filter((f) => f.key !== facet.key)
    const reachable = entries.filter((entry) =>
      others.every((f) => picked[f.key] == null || entry[f.key] === picked[f.key]),
    )
    return [...new Set(reachable.map((e) => e[facet.key]))].sort()
  }

  const chip = (active: boolean) =>
    `text-xs font-display font-medium px-3 py-1 rounded-field transition-colors ${
      active
        ? 'bg-navy text-ivory'
        : 'border border-navy/20 text-navy/70 hover:bg-ivory'
    }`

  const card = (entry: RuleIndexEntry) => (
    <Link
      to={entry.path}
      className="block rounded-card border border-navy/10 bg-white p-4 hover:border-cyan transition-colors"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display font-medium text-navy">
          {t(`rulesPage.dir.${entry.direction}`)} {entry.jurisdiction_name}
        </p>
        <MonoText className="text-xs text-navy/45">
          {entry.reviewed_at
            ? t('rulesIndex.reviewedAt', { when: prefs.date(entry.reviewed_at) })
            : t('rulesIndex.neverReviewed')}
        </MonoText>
      </div>
      {entry.title && (
        <p className="text-sm font-body text-navy/60">{entry.title}</p>
      )}
      {/* What makes an entry an entry rather than a menu item. A reader who
          has been here before scans these lines and nothing else. */}
      {entry.published_note && (
        <p className="mt-1 text-sm font-body text-navy/70 border-l-2 border-cyan/40 pl-3">
          {entry.published_note}
        </p>
      )}
      {/* Said before the click, because it is what the reader is deciding
          about: a corridor answering twelve questions is a different offer
          from one that has only the legal text. */}
      {entry.question_count > 0 && (
        <MonoText className="mt-2 inline-block text-[11px] text-cyan">
          {t('rulesIndex.answersCount', { count: entry.question_count })}
        </MonoText>
      )}
    </Link>
  )

  const chronological = (rows: RuleIndexEntry[]) => (
    <ul className="space-y-2">
      {rows.map((entry) => (
        <li key={entry.path}>{card(entry)}</li>
      ))}
    </ul>
  )

  const byCategory = (rows: RuleIndexEntry[]) => {
    const grouped = rows.reduce<Record<string, RuleIndexEntry[]>>((acc, entry) => {
      ;(acc[entry.category_key] ??= []).push(entry)
      return acc
    }, {})
    return Object.entries(grouped).map(([category, group]) => (
      <section key={category} className="space-y-3">
        <h2 className="font-display font-semibold text-xl text-navy">
          {t(`categories.${category}`, { defaultValue: category })}
        </h2>
        <ul className="space-y-2">
          {group.map((entry) => (
            <li key={entry.path}>{card(entry)}</li>
          ))}
        </ul>
      </section>
    ))
  }

  const anyPicked = facets.some((f) => picked[f.key] != null)

  return (
    <LandingShell source="sender">
      {() => (
        <div className="max-w-3xl mx-auto px-4 py-10 space-y-8">
          <header className="space-y-2">
            <h1 className="font-display font-bold text-3xl text-navy">
              {t('rulesIndex.title')}
            </h1>
            <p className="text-sm font-body text-navy/70 leading-relaxed">
              {t('rulesIndex.lede')}
            </p>
          </header>

          {failed && (
            <p className="text-xs font-mono text-danger">{t('rulesIndex.failed')}</p>
          )}

          {entries !== null && entries.length > 0 && (
            <div className="rounded-card border border-navy/10 bg-white p-4 space-y-3">
              {facets.map((facet) => {
                const options = optionsFor(facet)
                // A dimension with one value is not a choice. Showing it would
                // be a control that cannot change anything on the screen.
                if (options.length < 2) return null
                return (
                  <div key={facet.key} className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-body text-navy/50 w-24 shrink-0">
                      {t(`rulesIndex.facet.${facet.key}`)}
                    </span>
                    <button
                      onClick={() => setPicked((p) => ({ ...p, [facet.key]: null }))}
                      aria-pressed={picked[facet.key] == null}
                      className={chip(picked[facet.key] == null)}
                    >
                      {t('rulesIndex.facet.any')}
                    </button>
                    {options.map((value) => (
                      <button
                        key={value}
                        onClick={() =>
                          setPicked((p) => ({
                            ...p,
                            // Pressing the active chip clears it. Without this
                            // the only way back is the "any" chip, and people
                            // press the lit one to turn it off.
                            [facet.key]: p[facet.key] === value ? null : value,
                          }))
                        }
                        aria-pressed={picked[facet.key] === value}
                        className={chip(picked[facet.key] === value)}
                      >
                        {facet.label(value, entries)}
                      </button>
                    ))}
                  </div>
                )
              })}

              <div className="flex flex-wrap items-center gap-2 border-t border-navy/10 pt-3">
                <span className="text-xs font-body text-navy/50 w-24 shrink-0">
                  {t('rulesIndex.sortLabel')}
                </span>
                {(['chronological', 'category'] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setSort(option)}
                    aria-pressed={sort === option}
                    className={chip(sort === option)}
                  >
                    {t(`rulesIndex.sort.${option}`)}
                  </button>
                ))}
              </div>

              {anyPicked && (
                <p className="text-xs font-body text-navy/50">
                  {t('rulesIndex.showingCount', {
                    shown: shown.length,
                    total: entries.length,
                  })}
                </p>
              )}
            </div>
          )}

          {entries === null ? (
            <p className="text-sm font-body text-navy/40">{t('common.loading')}</p>
          ) : entries.length === 0 ? (
            <div className="rounded-card border border-navy/10 bg-white p-6 space-y-2">
              <p className="font-display font-medium text-navy">
                {t('rulesIndex.emptyTitle')}
              </p>
              {/* Says what to do rather than only that there is nothing. The
                  corridors written next are the ones people ask about. */}
              <p className="text-sm font-body text-navy/60">
                {t('rulesIndex.emptyBody')}
              </p>
            </div>
          ) : shown.length === 0 ? (
            // Reachable only if a filter combination empties the list, which
            // `optionsFor` is built to prevent — kept because "prevented by
            // construction" is a claim, and an empty screen with no sentence
            // on it is the worst way to discover the claim was wrong.
            <div className="rounded-card border border-navy/10 bg-white p-6 space-y-2">
              <p className="font-display font-medium text-navy">
                {t('rulesIndex.noMatchTitle')}
              </p>
              <button
                onClick={() =>
                  setPicked({
                    category_key: null,
                    direction: null,
                    jurisdiction_code: null,
                  })
                }
                className="text-sm font-body text-cyan hover:underline"
              >
                {t('rulesIndex.clearFilters')}
              </button>
            </div>
          ) : sort === 'chronological' ? (
            chronological(shown)
          ) : (
            <div className="space-y-8">{byCategory(shown)}</div>
          )}

          <p className="text-xs font-body text-navy/50 border-t border-navy/10 pt-4">
            {t('rulesIndex.disclaimer')}
          </p>
        </div>
      )}
    </LandingShell>
  )
}
