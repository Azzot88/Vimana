import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { readRule, type PublicRuleSet } from '../api/rulesPublic'
import { usePrefs } from '../hooks/usePrefs'
import LandingShell from '../components/landing/LandingShell'
import MonoText from '../components/MonoText'

/**
 * T3.11.03 — one corridor's rules, read by anybody.
 *
 * No session anywhere on this page. It is the free half of stream D
 * (`MASTERPLAN §4.1`): what is sold is the collected packet, not the knowledge,
 * and knowledge behind a sign-in is knowledge nobody reads.
 *
 * **Three things are stated on the page rather than assumed.**
 *
 * Every claim shows its citation — the authority, the document and a verbatim
 * quotation. That is what separates this from a plausible page: an uncited rule
 * reads, to somebody who needs it, exactly like a cited one.
 *
 * The date a **person** last checked it is next to the text, not in a footer.
 * A rule that quietly went stale is the most expensive defect this whole block
 * can produce, because the reader believes they have prepared.
 *
 * When a section has not been translated yet, the page says so on that section
 * instead of showing English as though it were the translation.
 *
 * Rendered inside `LandingShell` (T_UX.23) so a visitor arriving from a search
 * lands on something that is recognisably the same product, with a way onward.
 */
export default function RulesPage({ initial }: { initial?: PublicRuleSet }) {
  const { t, i18n } = useTranslation()
  const prefs = usePrefs()
  const params = useParams<{ category: string; direction: string; country: string }>()

  const [data, setData] = useState<PublicRuleSet | null>(initial ?? null)
  const [state, setState] = useState<'idle' | 'loading' | 'missing' | 'failed'>(
    initial ? 'idle' : 'loading',
  )

  useEffect(() => {
    // Prerendered markup is already correct for the first paint; the fetch
    // still runs so a page served from a file built last deploy refreshes
    // itself for a reader who is looking at it now.
    if (!params.category || !params.direction || !params.country) return
    readRule(params.category, params.direction, params.country, i18n.language)
      .then(({ data: fresh }) => {
        setData(fresh)
        setState('idle')
      })
      .catch((err: { response?: { status?: number } }) => {
        if (initial) return // keep what the file already showed
        setState(err?.response?.status === 404 ? 'missing' : 'failed')
      })
  }, [params.category, params.direction, params.country, i18n.language])

  const body = () => {
    if (state === 'loading') {
      return <p className="text-sm font-body text-navy/40">{t('common.loading')}</p>
    }
    if (state === 'missing' || (state === 'idle' && !data)) {
      return (
        <div className="space-y-2">
          <h1 className="font-display font-bold text-2xl text-navy">
            {t('rulesPage.missingTitle')}
          </h1>
          <p className="text-sm font-body text-navy/60">{t('rulesPage.missingBody')}</p>
        </div>
      )
    }
    if (state === 'failed' || !data) {
      return <p className="text-sm font-mono text-danger">{t('rulesPage.failed')}</p>
    }

    return (
      <article className="space-y-6">
        <header className="space-y-2">
          <MonoText className="text-xs text-navy/50">
            {t(`rulesPage.dir.${data.direction}`)} · {data.jurisdiction_name} ·{' '}
            {data.category_key}
          </MonoText>
          <h1 className="font-display font-bold text-3xl text-navy">
            {data.title || t('rulesPage.untitled')}
          </h1>

          {/* Freshness next to the claim, not under it. A rule that went stale
              in silence is the costliest thing this block can produce: the
              reader believes they have prepared. */}
          <div className="flex flex-wrap items-center gap-3">
            {data.reviewed_at ? (
              <MonoText className="text-xs text-navy/60">
                {t('rulesPage.reviewedAt', { when: prefs.date(data.reviewed_at) })}
              </MonoText>
            ) : (
              <MonoText className="text-xs text-amber">
                {t('rulesPage.neverReviewed')}
              </MonoText>
            )}
            {data.needs_review && (
              <span className="text-xs font-mono bg-amber/20 text-amber px-2 py-0.5 rounded">
                {t('rulesPage.needsReview')}
              </span>
            )}
          </div>

          {/* «Что изменилось» — то, что делает страницу читаемой во второй раз.
              Без этой строки вернувшийся видит только новую дату и не знает,
              стоит ли перечитывать. */}
          {data.published_note && (
            <p className="text-sm font-body text-navy/70 border-l-2 border-cyan/40 pl-3">
              {t('rulesPage.whatChanged')} {data.published_note}
            </p>
          )}

          {data.fallback_locale && (
            <p className="text-xs font-body text-navy/60 border border-navy/15 rounded-field px-3 py-2">
              {t('rulesPage.partiallyTranslated')}
            </p>
          )}
        </header>

        {data.sections.map((s) => (
          <section key={`${s.anchor}-${s.locale}`} id={s.anchor} className="space-y-2">
            <h2 className="font-display font-semibold text-xl text-navy">
              {s.title}
              {s.locale !== data.locale && (
                <span className="ml-2 text-xs font-mono text-navy/40">
                  {t('rulesPage.inLocale', { locale: s.locale.toUpperCase() })}
                </span>
              )}
            </h2>
            <p className="text-sm font-body text-navy/80 whitespace-pre-wrap leading-relaxed">
              {s.body}
            </p>

            {/* The citation is the page's spine, not an appendix. */}
            {s.sources.map((src, i) => (
              <div
                key={`${s.anchor}-src-${i}`}
                className="rounded-field bg-ivory border border-navy/10 p-3 space-y-1"
              >
                <MonoText className="text-[11px] text-navy/60">
                  {src.authority} · {src.document_title}
                  {src.document_date ? ` · ${src.document_date}` : ''}
                </MonoText>
                <p className="text-xs font-body text-navy/70 italic">«{src.quote}»</p>
                {src.url && (
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noreferrer nofollow"
                    className="text-xs font-body text-cyan hover:underline"
                  >
                    {t('rulesPage.openSource')}
                  </a>
                )}
              </div>
            ))}
          </section>
        ))}

        {data.requirements.length > 0 && (
          <section className="space-y-3">
            <h2 className="font-display font-semibold text-xl text-navy">
              {t('rulesPage.documentsTitle')}
            </h2>
            <p className="text-sm font-body text-navy/60">
              {t('rulesPage.documentsHint')}
            </p>
            <ul className="space-y-2">
              {data.requirements.map((r) => (
                <li
                  key={r.code}
                  className="rounded-field border border-navy/10 p-3 space-y-0.5"
                >
                  <p className="font-display font-medium text-sm text-navy">{r.title}</p>
                  <p className="text-xs font-body text-navy/60">
                    {r.issuer || t('rulesPage.issuerUnknown')}
                    {r.lead_time_days != null &&
                      ` · ${t('rulesPage.leadDays', { days: r.lead_time_days })}`}
                    {r.valid_for_days != null &&
                      ` · ${t('rulesPage.validDays', { days: r.valid_for_days })}`}
                  </p>
                  {!r.is_mandatory && (
                    <MonoText className="text-[11px] text-navy/45">
                      {t('rulesPage.conditional')}
                    </MonoText>
                  )}
                  {r.notes && (
                    <p className="text-xs font-body text-navy/60">{r.notes}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* §9.1 — what this page is and is not. Said once, plainly, at the end:
            the platform is not a broker and does not issue any of these. */}
        <p className="text-xs font-body text-navy/50 border-t border-navy/10 pt-4">
          {t('rulesPage.disclaimer')}
        </p>
      </article>
    )
  }

  // `source="sender"` — somebody reading how to take a painting out of Russia
  // is a sender, and the waitlist entry should say so rather than pool every
  // rules reader under a fourth source that means nothing to whoever reads it.
  return (
    <LandingShell source="sender">
      {() => <div className="max-w-3xl mx-auto px-4 py-10">{body()}</div>}
    </LandingShell>
  )
}
