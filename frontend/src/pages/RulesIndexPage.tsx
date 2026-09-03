import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { bootstrapped, rulesIndex, type RuleIndexEntry } from '../api/rulesPublic'
import { usePrefs } from '../hooks/usePrefs'
import { freshnessOf } from '../lib/format'
import LandingShell from '../components/landing/LandingShell'
import Breadcrumbs from '../components/Breadcrumbs'
import MonoText from '../components/MonoText'

/**
 * T3.11.03 pt.2 / T3.11.05 pt.2 — the catalogue of corridors.
 *
 * ## What this page is for
 *
 * Two readers arrive here and they need opposite things from the same screen.
 * A carrier who does this route monthly knows their corridor and wants the date
 * it was last checked, in about three seconds. Somebody taking a painting
 * abroad for the first time does not know the taxonomy at all: "art / export /
 * RU" tells them nothing, because they do not think in categories, they think
 * in questions.
 *
 * That tension is the whole design. The catalogue therefore lists **real
 * questions inside each corridor entry** rather than a count of them. The
 * beginner recognises their own question in the list; the professional reads
 * the corridor code and the date and skims past. One layout, both jobs, no
 * toggle between two modes of the same page.
 *
 * ## Why not the obvious alternatives
 *
 * A matrix of category by country shows the shape of the corpus, and at four
 * corridors it is mostly empty cells that read as unfinished work. A two-pane
 * browser with a filter rail scales to fifty corridors and, applied to four,
 * is an interface pretending to have a problem it does not have. Rows grow;
 * layouts that assume volume do not degrade gracefully when the volume is not
 * there yet.
 *
 * ## The controls
 *
 * **Search is primary** and runs over question text as well as corridor titles,
 * because "нужно ли разрешение" is what somebody types, not "art export". When
 * a search is running the page reorganises into matched questions grouped by
 * corridor, each linking straight to its answer anchor. That is a different
 * question than "which corridors exist", so it gets a different presentation
 * rather than a filtered version of the same list.
 *
 * **Filters are derived from the data, never from a list in this file.** A
 * hard-coded `['US','RU']` is correct the day it is written and silently wrong
 * the day somebody publishes a third country, because a missing chip looks
 * exactly like a corridor that does not exist. Each dimension also offers only
 * values still reachable given the other choices: a chip that can only empty
 * the screen is worse than an absent one, since pressing it reads as "there is
 * nothing here".
 *
 * **Sorting is visually separate from filtering.** They do different things and
 * looked identical before: one narrows the set, the other reorders it.
 *
 * ## Freshness
 *
 * The date a person last checked the text against its source is the claim this
 * whole section rests on, so it is printed twice: how long ago, and when. A
 * bare "12.01.2026" and a bare "30.08.2026" look the same at a glance, and the
 * difference between them is the difference between a page worth trusting and
 * one that is quietly eight months out of date.
 */
type Sort = 'chronological' | 'category'

type FacetKey = 'category_key' | 'direction' | 'jurisdiction_code'

const FACETS: FacetKey[] = ['category_key', 'direction', 'jurisdiction_code']

const EMPTY: Record<FacetKey, string | null> = {
  category_key: null,
  direction: null,
  jurisdiction_code: null,
}

export default function RulesIndexPage({ initial }: { initial?: RuleIndexEntry[] }) {
  const { t, i18n } = useTranslation()
  const prefs = usePrefs()
  // `initial` on the server, the payload it shipped on the client. Both must
  // produce the same first render or hydration throws the server's markup away
  // and paints a skeleton over a finished page (T_OPS.2).
  const seed = initial ?? bootstrapped<RuleIndexEntry[]>()
  const [entries, setEntries] = useState<RuleIndexEntry[] | null>(seed ?? null)
  const [failed, setFailed] = useState(false)
  const [sort, setSort] = useState<Sort>('chronological')
  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<Record<FacetKey, string | null>>(EMPTY)

  useEffect(() => {
    // Guarded because a locale switch starts a second request while the first
    // is still in flight, and without this the slower one wins by landing last.
    let live = true
    rulesIndex(i18n.language)
      .then(({ data }) => {
        if (live) setEntries(data)
      })
      .catch(() => {
        if (!live) return
        // Not silently empty: "nothing published yet" and "the request died"
        // look identical on screen, and the second reads as the first.
        //
        // The error line is shown only when there is nothing else to show. On a
        // prerendered page the build-time catalogue is already on screen and
        // still correct; printing a red failure line above it would tell the
        // reader that what they are reading is broken, which it is not.
        if (!seed) {
          setEntries([])
          setFailed(true)
        }
      })
    return () => {
      live = false
    }
    // `seed` is fixed at mount and never changes, so it is read here rather
    // than tracked.
  }, [i18n.language])

  const label = (key: FacetKey, value: string, rows: RuleIndexEntry[]): string => {
    if (key === 'category_key') return t(`categories.${value}`, { defaultValue: value })
    if (key === 'direction') return t(`rulesPage.dir.${value}`, { defaultValue: value })
    // The country's own name, taken from the row rather than from a map in this
    // file: the API already knows it, and a second copy is a second place to
    // forget a country.
    return rows.find((r) => r.jurisdiction_code === value)?.jurisdiction_name || value
  }

  const needle = query.trim().toLocaleLowerCase()

  const filtered = useMemo(() => {
    if (!entries) return []
    return entries.filter((e) => FACETS.every((k) => picked[k] == null || e[k] === picked[k]))
  }, [entries, picked])

  /** Corridors whose title or any question matches the search. */
  const searched = useMemo(() => {
    if (!needle) return filtered
    return filtered.filter(
      (e) =>
        e.title.toLocaleLowerCase().includes(needle) ||
        e.jurisdiction_name.toLocaleLowerCase().includes(needle) ||
        e.questions.some((q) => q.question.toLocaleLowerCase().includes(needle)),
    )
  }, [filtered, needle])

  /** Values of one dimension still reachable given the other picks. */
  const optionsFor = (key: FacetKey): string[] => {
    if (!entries) return []
    const reachable = entries.filter((e) =>
      FACETS.filter((k) => k !== key).every((k) => picked[k] == null || e[k] === picked[k]),
    )
    return [...new Set(reachable.map((e) => e[key]))].sort()
  }

  const chip = (active: boolean) =>
    `rounded-field px-3 py-1 text-xs font-display font-medium transition-colors ` +
    `` +
    `active:translate-y-px ` +
    (active
      ? 'bg-navy text-ivory'
      : 'border border-navy/20 text-navy/70 hover:border-navy/40 hover:bg-white')

  /** "Проверено вчера · 30.08.2026", plus a warning when that was long ago. */
  const checked = (iso: string | null) => {
    const fresh = freshnessOf(iso)
    if (!fresh) {
      return (
        <MonoText className="text-[11px] text-amber">
          {t('rulesIndex.neverReviewed')}
        </MonoText>
      )
    }
    return (
      <MonoText
        className={`text-[11px] ${fresh.stale ? 'text-amber' : 'text-navy/45'}`}
      >
        {/* Zero is its own sentence, not a plural form: i18next selects a zero
            category only for languages that have one, so "0 дней назад" is
            what a count-based key would print today. */}
        {fresh.days === 0
          ? t('rulesIndex.checkedToday')
          : t('rulesIndex.checkedAgo', { count: fresh.days })}
        <span className="text-navy/30"> · {prefs.date(iso)}</span>
      </MonoText>
    )
  }

  /**
   * One corridor. A row with a rule above it, not a card.
   *
   * Cards were the previous shape and they flattened the page: a corridor
   * answering eight questions looked exactly like one carrying only legal text,
   * because a border and a shadow say the same thing about every row they wrap.
   * The hairline groups, and the content inside carries the difference.
   */
  const row = (entry: RuleIndexEntry) => {
    const preview = entry.questions.slice(0, 3)
    const rest = entry.questions.length - preview.length
    return (
      <article className="border-t border-navy/10 py-6 first:border-t-0 sm:py-7">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          {/* A departure-board line, which is the brand's own device and
              carries more than a flag would: the arrow points the way the
              goods travel, so `RU →` is out of Russia and `→ US` is into the
              States. Country codes also survive every platform; emoji flags
              render as bare letters on Windows. */}
          <MonoText className="text-[11px] uppercase tracking-[0.14em] text-cyan">
            {entry.direction === 'export'
              ? `${entry.jurisdiction_code} →`
              : `→ ${entry.jurisdiction_code}`}
            <span className="text-navy/35">
              {' · '}
              {t(`categories.${entry.category_key}`, {
                defaultValue: entry.category_key,
              })}
            </span>
          </MonoText>
          {checked(entry.reviewed_at)}
        </div>

        <h3 className="mt-1 font-display text-xl font-semibold leading-tight tracking-tight text-navy sm:text-2xl">
          <Link to={entry.path} className="transition-colors hover:text-cyan">
            {entry.title || t('rulesPage.untitled')}
          </Link>
        </h3>

        {entry.published_note && (
          <p className="mt-2 max-w-[65ch] border-l-2 border-cyan/40 pl-3 text-sm font-body leading-relaxed text-navy/70">
            {entry.published_note}
          </p>
        )}

        {/* The point of the whole row. Real questions, so a reader who does not
            think in categories can still recognise their own problem. */}
        {preview.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {preview.map((q) => (
              <li key={q.anchor}>
                <Link
                  to={`${entry.path}#${q.anchor}`}
                  className="block max-w-[62ch] text-sm font-body leading-snug text-navy/75 underline decoration-navy/15 underline-offset-4 transition-colors hover:text-navy hover:decoration-cyan"
                >
                  {q.question}
                </Link>
              </li>
            ))}
          </ul>
        )}

        {/* Only when it says something the title link does not. Two links to
            the same page in one row, differing only in wording, is a control
            that adds a decision without adding a choice. */}
        {(rest > 0 || preview.length === 0) && (
          <Link
            to={entry.path}
            className="mt-3 inline-block text-sm font-display font-medium text-cyan transition-colors hover:text-navy"
          >
            {rest > 0
              ? t('rulesIndex.openWithRest', { count: rest })
              : t('rulesIndex.open')}
          </Link>
        )}
      </article>
    )
  }

  /** Search results: the questions themselves, grouped by where they live. */
  const results = (rows: RuleIndexEntry[]) => (
    <div className="space-y-8">
      {rows.map((entry) => {
        const hits = entry.questions.filter((q) =>
          q.question.toLocaleLowerCase().includes(needle),
        )
        return (
          <section key={entry.path}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 border-b border-navy/10 pb-2">
              <h3 className="font-display text-base font-semibold text-navy">
                <Link
                  to={entry.path}
                  className="transition-colors hover:text-cyan"
                >
                  {entry.title || t('rulesPage.untitled')}
                </Link>
              </h3>
              {checked(entry.reviewed_at)}
            </div>
            {hits.length === 0 ? (
              // The corridor matched by its title, not by a question. Saying so
              // is better than showing a heading with nothing under it.
              <p className="pt-2 text-sm font-body text-navy/50">
                {t('rulesIndex.matchedByTitle')}
              </p>
            ) : (
              <ul className="divide-y divide-navy/5">
                {hits.map((q) => (
                  <li key={q.anchor}>
                    <Link
                      to={`${entry.path}#${q.anchor}`}
                      className="block py-2.5 text-sm font-body leading-snug text-navy/80 transition-colors hover:text-navy"
                    >
                      {q.question}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )
      })}
    </div>
  )

  const byCategory = (rows: RuleIndexEntry[]) => {
    const grouped = rows.reduce<Record<string, RuleIndexEntry[]>>((acc, entry) => {
      ;(acc[entry.category_key] ??= []).push(entry)
      return acc
    }, {})
    return Object.entries(grouped).map(([category, group]) => (
      <section key={category}>
        <h2 className="font-display text-lg font-semibold tracking-tight text-navy">
          {t(`categories.${category}`, { defaultValue: category })}
        </h2>
        <div className="mt-3">{group.map((e) => <div key={e.path}>{row(e)}</div>)}</div>
      </section>
    ))
  }

  /** Skeleton shaped like a corridor row, not a spinner. */
  const skeleton = (
    <div aria-hidden="true" className="animate-pulse">
      {[0, 1, 2].map((i) => (
        <div key={i} className="border-t border-navy/10 py-7 first:border-t-0">
          <div className="h-2 w-28 rounded bg-navy/10" />
          <div className="mt-3 h-5 w-2/3 rounded bg-navy/10" />
          <div className="mt-4 h-3 w-5/6 rounded bg-navy/5" />
          <div className="mt-2 h-3 w-3/4 rounded bg-navy/5" />
        </div>
      ))}
    </div>
  )

  const anyPicked = FACETS.some((k) => picked[k] != null)
  const totals = entries ?? []
  const questionTotal = totals.reduce((n, e) => n + e.question_count, 0)

  return (
    <LandingShell source="sender">
      {(openWaitlist) => (
        // Back to the measure the page had before the rebuild (owner's
        // decision 2026-09-02). The catalogue has no side rail, so the cap is
        // simply the reading width and holds at every size.
        <div className="mx-auto max-w-3xl py-8 sm:py-12">
          <Breadcrumbs
            items={[
              { label: t('rulesIndex.crumbHome'), to: '/' },
              { label: t('rulesIndex.navLink') },
            ]}
          />

          <header className="mt-5 max-w-[46ch]">
            <h1 className="font-display text-4xl font-bold leading-[1.05] tracking-tight text-navy sm:text-5xl">
              {t('rulesIndex.title')}
            </h1>
            <p className="mt-4 max-w-[62ch] text-base font-body leading-relaxed text-navy/70">
              {t('rulesIndex.lede')}
            </p>
          </header>

          {/* The scale of the corpus, from the corpus. This is the trust
              signal for a reference work, and every number here is counted
              from the data rather than written into the copy. */}
          {totals.length > 0 && (
            <MonoText className="mt-5 block text-xs text-navy/45">
              {/* Two keys, not one string with two numbers in it: i18next
                  pluralises on a single `count`, so a combined line could only
                  ever be right for one of them. "5 коридора" is the shape of
                  that bug in Russian. */}
              {t('rulesIndex.scaleCorridors', { count: totals.length })}
              {' · '}
              {t('rulesIndex.scaleQuestions', { count: questionTotal })}
            </MonoText>
          )}

          {failed && (
            <p className="mt-6 text-xs font-mono text-danger">{t('rulesIndex.failed')}</p>
          )}

          {totals.length > 0 && (
            <div className="mt-8 border-y border-navy/10 py-5">
              <label className="block">
                <span className="text-xs font-body text-navy/50">
                  {t('rulesIndex.searchLabel')}
                </span>
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t('rulesIndex.searchPlaceholder') as string}
                  className="mt-1.5 w-full rounded-field border border-navy/20 bg-white px-3 py-2.5 text-base font-body text-navy placeholder:text-navy/60 transition-colors focus:border-cyan focus:outline-none"
                />
              </label>

              <div className="mt-4 space-y-2">
                {FACETS.map((key) => {
                  const options = optionsFor(key)
                  // A dimension with one value is not a choice. Showing it
                  // would be a control that cannot change the screen.
                  if (options.length < 2) return null
                  return (
                    <div key={key} className="flex flex-wrap items-center gap-1.5">
                      <span className="w-24 shrink-0 text-xs font-body text-navy/45">
                        {t(`rulesIndex.facet.${key}`)}
                      </span>
                      <button
                        type="button"
                        onClick={() => setPicked((p) => ({ ...p, [key]: null }))}
                        aria-pressed={picked[key] == null}
                        className={chip(picked[key] == null)}
                      >
                        {t('rulesIndex.facet.any')}
                      </button>
                      {options.map((value) => (
                        <button
                          key={value}
                          type="button"
                          onClick={() =>
                            setPicked((p) => ({
                              // Pressing the lit chip clears it. Without this
                              // the only way back is the "any" chip, and people
                              // press the lit one to turn it off.
                              ...p,
                              [key]: p[key] === value ? null : value,
                            }))
                          }
                          aria-pressed={picked[key] === value}
                          className={chip(picked[key] === value)}
                        >
                          {label(key, value, totals)}
                        </button>
                      ))}
                    </div>
                  )
                })}
              </div>

              {/* Ordering, kept visually apart from filtering: one narrows the
                  set, the other rearranges it, and they looked identical. */}
              {!needle && (
                <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-navy/5 pt-4">
                  <span className="w-24 shrink-0 text-xs font-body text-navy/45">
                    {t('rulesIndex.sortLabel')}
                  </span>
                  {(['chronological', 'category'] as const).map((option) => (
                    <button
                      key={option}
                      type="button"
                      onClick={() => setSort(option)}
                      aria-pressed={sort === option}
                      className={chip(sort === option)}
                    >
                      {t(`rulesIndex.sort.${option}`)}
                    </button>
                  ))}
                </div>
              )}

              {(anyPicked || needle) && (
                <p className="mt-4 flex flex-wrap items-center gap-3 text-xs font-body text-navy/50">
                  <span>
                    {t('rulesIndex.showingCount', {
                      shown: searched.length,
                      total: totals.length,
                    })}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setPicked(EMPTY)
                      setQuery('')
                    }}
                    className="text-cyan underline underline-offset-2 transition-colors hover:text-navy"
                  >
                    {t('rulesIndex.clearFilters')}
                  </button>
                </p>
              )}
            </div>
          )}

          <div className="mt-8">
            {entries === null ? (
              skeleton
            ) : entries.length === 0 ? (
              <div className="max-w-[60ch] space-y-3">
                <h2 className="font-display text-xl font-semibold text-navy">
                  {t('rulesIndex.emptyTitle')}
                </h2>
                {/* Says what to do rather than only that there is nothing. */}
                <p className="text-sm font-body leading-relaxed text-navy/60">
                  {t('rulesIndex.emptyBody')}
                </p>
              </div>
            ) : searched.length === 0 ? (
              <div className="max-w-[60ch] space-y-3">
                <h2 className="font-display text-xl font-semibold text-navy">
                  {t('rulesIndex.noMatchTitle')}
                </h2>
                <p className="text-sm font-body leading-relaxed text-navy/60">
                  {t('rulesIndex.noMatchBody')}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setPicked(EMPTY)
                    setQuery('')
                  }}
                  className="text-sm font-display font-medium text-cyan transition-colors hover:text-navy"
                >
                  {t('rulesIndex.clearFilters')}
                </button>
              </div>
            ) : needle ? (
              results(searched)
            ) : sort === 'chronological' ? (
              <div>{searched.map((e) => <div key={e.path}>{row(e)}</div>)}</div>
            ) : (
              <div className="space-y-10">{byCategory(searched)}</div>
            )}
          </div>

          {/* The next step. It belongs here as well as on the corridor pages:
              this is the page people arrive at from a search, and a catalogue
              that ends in a disclaimer is a catalogue that reads everything and
              leaves.

              Same label as the corridor page on purpose. One label per intent,
              used everywhere, is what keeps a reader from wondering whether two
              buttons do two different things. */}
          {totals.length > 0 && (
            <section className="mt-12 rounded-card border border-amber/30 bg-amber/5 p-5">
              <h2 className="font-display text-lg font-semibold text-navy">
                {t('rulesPage.packetTitle')}
              </h2>
              <p className="mt-2 max-w-[60ch] text-sm font-body leading-relaxed text-navy/70">
                {t('rulesPage.packetBody')}
              </p>
              <button
                type="button"
                onClick={openWaitlist}
                className="mt-4 rounded-field bg-amber px-4 py-2 text-sm font-display font-medium text-white transition-opacity hover:opacity-90 active:translate-y-px"
              >
                {t('rulesPage.packetCta')}
              </button>
            </section>
          )}

          {/* What the catalogue does not cover, said out loud. On a page about
              somebody else's border this is not a weakness to hide: a reader
              who assumes a gap is covered is the one who gets hurt by it. */}
          <section className="mt-14 max-w-[65ch] border-t border-navy/10 pt-6">
            <h2 className="font-display text-base font-semibold text-navy">
              {t('rulesIndex.gapsTitle')}
            </h2>
            <p className="mt-2 text-sm font-body leading-relaxed text-navy/65">
              {t('rulesIndex.gapsBody')}
            </p>
          </section>

          <p className="mt-8 max-w-[65ch] text-xs font-body leading-relaxed text-navy/45">
            {t('rulesIndex.disclaimer')}
          </p>
        </div>
      )}
    </LandingShell>
  )
}
