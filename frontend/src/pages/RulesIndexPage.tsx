import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { rulesIndex, type RuleIndexEntry } from '../api/rulesPublic'
import { usePrefs } from '../hooks/usePrefs'
import LandingShell from '../components/landing/LandingShell'
import MonoText from '../components/MonoText'

/**
 * T3.11.03 pt.2 — the way in.
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
 */
type Sort = 'chronological' | 'category'

export default function RulesIndexPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [entries, setEntries] = useState<RuleIndexEntry[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [sort, setSort] = useState<Sort>('chronological')

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
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-body text-navy/50">
                {t('rulesIndex.sortLabel')}
              </span>
              {(['chronological', 'category'] as const).map((option) => (
                <button
                  key={option}
                  onClick={() => setSort(option)}
                  aria-pressed={sort === option}
                  className={`text-xs font-display font-medium px-3 py-1 rounded-field transition-colors ${
                    sort === option
                      ? 'bg-navy text-ivory'
                      : 'border border-navy/20 text-navy/70 hover:bg-ivory'
                  }`}
                >
                  {t(`rulesIndex.sort.${option}`)}
                </button>
              ))}
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
          ) : sort === 'chronological' ? (
            chronological(entries)
          ) : (
            <div className="space-y-8">{byCategory(entries)}</div>
          )}

          <p className="text-xs font-body text-navy/50 border-t border-navy/10 pt-4">
            {t('rulesIndex.disclaimer')}
          </p>
        </div>
      )}
    </LandingShell>
  )
}
