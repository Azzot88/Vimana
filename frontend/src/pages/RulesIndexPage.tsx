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
 * pointed at. This is the page a link from the landing lands on, and the page a
 * crawler follows to find the rest.
 *
 * **Grouped by category, not by country**, for the same reason the address puts
 * the category first: people arrive with a thing, not with a border. Somebody
 * holding a painting looks for paintings; the direction and the country narrow
 * it afterwards.
 *
 * The date a person last checked each corridor is on the card. A directory that
 * lists twelve corridors without saying which of them was read this year is a
 * directory that ages invisibly.
 */
export default function RulesIndexPage() {
  const { t } = useTranslation()
  const prefs = usePrefs()
  const [entries, setEntries] = useState<RuleIndexEntry[] | null>(null)
  const [failed, setFailed] = useState(false)

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

  const byCategory = (entries ?? []).reduce<Record<string, RuleIndexEntry[]>>(
    (acc, entry) => {
      ;(acc[entry.category_key] ??= []).push(entry)
      return acc
    },
    {},
  )

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
          ) : (
            Object.entries(byCategory).map(([category, rows]) => (
              <section key={category} className="space-y-3">
                <h2 className="font-display font-semibold text-xl text-navy">
                  {t(`categories.${category}`, { defaultValue: category })}
                </h2>
                <ul className="space-y-2">
                  {rows.map((entry) => (
                    <li key={entry.path}>
                      <Link
                        to={entry.path}
                        className="block rounded-card border border-navy/10 bg-white p-4 hover:border-cyan transition-colors"
                      >
                        <p className="font-display font-medium text-navy">
                          {t(`rulesPage.dir.${entry.direction}`)}{' '}
                          {entry.jurisdiction_name}
                        </p>
                        {entry.title && (
                          <p className="text-sm font-body text-navy/60">{entry.title}</p>
                        )}
                        <MonoText className="text-xs text-navy/45">
                          {entry.reviewed_at
                            ? t('rulesIndex.reviewedAt', {
                                when: prefs.date(entry.reviewed_at),
                              })
                            : t('rulesIndex.neverReviewed')}
                        </MonoText>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}

          <p className="text-xs font-body text-navy/50 border-t border-navy/10 pt-4">
            {t('rulesIndex.disclaimer')}
          </p>
        </div>
      )}
    </LandingShell>
  )
}
