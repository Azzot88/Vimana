import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { readRule, type PublicRuleSet } from '../api/rulesPublic'
import { usePrefs } from '../hooks/usePrefs'
import { freshnessOf } from '../lib/format'
import { renderMarkdown } from '../lib/markdown'
import LandingShell from '../components/landing/LandingShell'
import Breadcrumbs from '../components/Breadcrumbs'
import MonoText from '../components/MonoText'

/**
 * T3.11.03 / T3.11.05 pt.2 — one corridor's rules, read by anybody.
 *
 * No session anywhere on this page. It is the free half of stream D
 * (`MASTERPLAN §4.1`): what is sold is the collected packet, not the knowledge,
 * and knowledge behind a sign-in is knowledge nobody reads.
 *
 * ## The page in three claims
 *
 * **Every claim shows its citation** - the authority, the document, and a
 * verbatim quotation. That is what separates this from a plausible page: an
 * uncited rule reads, to somebody who needs it, exactly like a cited one. So
 * the quotation is set as the anchor of its section rather than as a footnote,
 * and it is the one element on the page allowed to interrupt the prose.
 *
 * **The date a person last checked it** sits next to the text, in two forms:
 * how long ago, and when. "12.01.2026" and "30.08.2026" look identical at a
 * glance, and the difference between them decides whether the reader should
 * trust the page. Past half a year the page says so in its own voice.
 *
 * **A section not yet translated says so on itself**, instead of showing
 * English as though it were the translation.
 *
 * ## Order of the page
 *
 * Questions first, then the law, then the documents. The corpus below is
 * written as law, which is the right shape for something a reader has to be
 * able to check and the wrong shape for somebody deciding whether they can put
 * a painting in a suitcase on Thursday. Each short answer links down to the
 * section it compresses, and that link is what earns it the right to be short.
 *
 * The contents rail is the second half of the same idea: this is a reference
 * document, and a reference document read on a phone or scrolled to from a
 * search result needs a visible map of itself.
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
    // Guarded because switching language starts a second request while the
    // first is still in flight, and without this the slower one wins by
    // landing last.
    let live = true
    readRule(params.category, params.direction, params.country, i18n.language)
      .then(({ data: fresh }) => {
        if (!live) return
        setData(fresh)
        setState('idle')
      })
      .catch((err: { response?: { status?: number } }) => {
        if (!live || initial) return // keep what the file already showed
        setState(err?.response?.status === 404 ? 'missing' : 'failed')
      })
    return () => {
      live = false
    }
  }, [params.category, params.direction, params.country, i18n.language])

  const crumbs = (last: string) => [
    { label: t('rulesIndex.crumbHome'), to: '/' },
    { label: t('rulesIndex.navLink'), to: '/rules' },
    { label: last },
  ]

  const skeleton = (
    <div aria-hidden="true" className="animate-pulse space-y-4">
      <div className="h-2 w-32 rounded bg-navy/10" />
      <div className="h-9 w-3/4 rounded bg-navy/10" />
      <div className="h-3 w-40 rounded bg-navy/5" />
      <div className="mt-8 space-y-2">
        <div className="h-3 w-full rounded bg-navy/5" />
        <div className="h-3 w-11/12 rounded bg-navy/5" />
        <div className="h-3 w-4/5 rounded bg-navy/5" />
      </div>
    </div>
  )

  const body = () => {
    if (state === 'loading') return skeleton

    if (state === 'missing' || (state === 'idle' && !data)) {
      return (
        <>
          <Breadcrumbs items={crumbs(t('rulesPage.missingCrumb'))} />
          <div className="mt-5 max-w-[60ch] space-y-3">
            <h1 className="font-display text-3xl font-bold tracking-tight text-navy">
              {t('rulesPage.missingTitle')}
            </h1>
            <p className="text-sm font-body leading-relaxed text-navy/65">
              {t('rulesPage.missingBody')}
            </p>
          </div>
        </>
      )
    }
    if (state === 'failed' || !data) {
      return (
        <>
          <Breadcrumbs items={crumbs(t('rulesPage.missingCrumb'))} />
          <p className="mt-5 font-mono text-sm text-danger">{t('rulesPage.failed')}</p>
        </>
      )
    }

    const fresh = freshnessOf(data.reviewed_at)
    const category = t(`categories.${data.category_key}`, {
      defaultValue: data.category_key,
    })

    return (
      <article>
        <Breadcrumbs
          items={[
            { label: t('rulesIndex.crumbHome'), to: '/' },
            { label: t('rulesIndex.navLink'), to: '/rules' },
            { label: category, to: '/rules' },
            {
              label: `${t(`rulesPage.dir.${data.direction}`)} ${data.jurisdiction_name}`,
            },
          ]}
        />

        <header className="mt-5">
          {/* The same departure-board line as the catalogue row, so a reader
              arriving from there recognises where they landed. The arrow points
              the way the goods travel. */}
          <MonoText className="text-[11px] uppercase tracking-[0.14em] text-cyan">
            {data.direction === 'export'
              ? `${data.jurisdiction_code} →`
              : `→ ${data.jurisdiction_code}`}
            <span className="text-navy/35">
              {' · '}
              {category}
            </span>
          </MonoText>

          <h1 className="mt-2 max-w-[22ch] font-display text-4xl font-bold leading-[1.05] tracking-tight text-navy sm:text-5xl">
            {data.title || t('rulesPage.untitled')}
          </h1>

          {/* Freshness beside the claim, not under it. A rule that went stale
              in silence is the costliest thing this block can produce: the
              reader believes they have prepared. */}
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
            {fresh ? (
              <MonoText
                className={`text-xs ${fresh.stale ? 'text-amber' : 'text-navy/55'}`}
              >
                {fresh.days === 0
                  ? t('rulesPage.checkedToday')
                  : t('rulesPage.checkedAgo', { count: fresh.days })}
                <span className="text-navy/35"> · {prefs.date(data.reviewed_at)}</span>
              </MonoText>
            ) : (
              <MonoText className="text-xs text-amber">
                {t('rulesPage.neverReviewed')}
              </MonoText>
            )}
            {fresh?.stale && (
              <span className="rounded-field bg-amber/10 px-2 py-0.5 text-[11px] font-body text-amber">
                {t('rulesPage.staleWarning')}
              </span>
            )}
            {data.needs_review && (
              <span className="rounded-field bg-amber/15 px-2 py-0.5 text-[11px] font-body text-amber">
                {t('rulesPage.needsReview')}
              </span>
            )}
          </div>

          {data.published_note && (
            <p className="mt-4 max-w-[65ch] border-l-2 border-cyan/40 pl-3 text-sm font-body leading-relaxed text-navy/70">
              <span className="text-navy/45">{t('rulesPage.whatChanged')} </span>
              {data.published_note}
            </p>
          )}

          {data.fallback_locale && (
            <p className="mt-4 max-w-[65ch] rounded-field border border-navy/15 px-3 py-2 text-xs font-body leading-relaxed text-navy/60">
              {t('rulesPage.partiallyTranslated')}
            </p>
          )}
        </header>

        <div className="mt-10 lg:grid lg:grid-cols-[minmax(0,1fr)_13rem] lg:gap-10">
          <div className="min-w-0">
            {/* The compact reading, first. Rows under one heading rather than a
                grid of cards: these are questions in a list, and a card around
                each one would say they are separate objects when they are one
                conversation. */}
            {data.questions.length > 0 && (
              <section aria-labelledby="answers-h" className="scroll-mt-24" id="answers">
                <h2
                  id="answers-h"
                  className="font-display text-2xl font-semibold tracking-tight text-navy"
                >
                  {t('rulesPage.questionsTitle')}
                </h2>
                <p className="mt-1 max-w-[62ch] text-sm font-body text-navy/55">
                  {t('rulesPage.questionsHint')}
                </p>

                <div className="mt-5">
                  {data.questions.map((q) => (
                    <div
                      key={`${q.anchor}-${q.locale}`}
                      id={q.anchor}
                      className="scroll-mt-24 border-t border-navy/10 py-5 first:border-t-0 first:pt-0"
                    >
                      <h3 className="max-w-[58ch] font-display text-lg font-medium leading-snug text-navy">
                        {q.question}
                        {q.locale !== data.locale && (
                          <span className="ml-2 font-mono text-[11px] text-navy/40">
                            {t('rulesPage.inLocale', { locale: q.locale.toUpperCase() })}
                          </span>
                        )}
                      </h3>
                      <div
                        className="rules-prose mt-2 max-w-[65ch] text-[15px] font-body leading-relaxed text-navy/80"
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(q.answer) }}
                      />
                      <a
                        href={`#${q.section_anchor}`}
                        className="mt-2 inline-block text-xs font-body text-cyan transition-colors hover:text-navy"
                      >
                        {t('rulesPage.readTheRule', {
                          section:
                            data.sections.find((s) => s.anchor === q.section_anchor)
                              ?.title || q.section_anchor,
                        })}
                      </a>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section className="mt-14">
              <h2 className="font-display text-2xl font-semibold tracking-tight text-navy">
                {t('rulesPage.rulesTitle')}
              </h2>
              <p className="mt-1 max-w-[62ch] text-sm font-body text-navy/55">
                {t('rulesPage.rulesHint')}
              </p>

              <div className="mt-6 space-y-12">
                {data.sections.map((s) => (
                  <section key={`${s.anchor}-${s.locale}`} id={s.anchor} className="scroll-mt-24">
                    <h3 className="max-w-[34ch] font-display text-xl font-semibold leading-snug tracking-tight text-navy">
                      {s.title}
                      {s.locale !== data.locale && (
                        <span className="ml-2 font-mono text-[11px] font-normal text-navy/40">
                          {t('rulesPage.inLocale', { locale: s.locale.toUpperCase() })}
                        </span>
                      )}
                    </h3>
                    {/* `body` is Markdown, rendered with raw HTML disabled - see
                        `lib/markdown`. `dangerouslySetInnerHTML` is safe here
                        for a reason that is checkable rather than assumed: the
                        renderer cannot emit a tag the source did not spell in
                        Markdown, and Markdown has no syntax for a script. */}
                    <div
                      className="rules-prose mt-3 max-w-[65ch] text-[15px] font-body leading-relaxed text-navy/80"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(s.body) }}
                    />

                    {/* The citation is the spine of the page, not an appendix.
                        Set as a quotation with a rule down its side: it is the
                        one element allowed to interrupt the prose, because it
                        is what makes the prose above it checkable. */}
                    {s.sources.map((src, i) => (
                      <figure
                        key={`${s.anchor}-src-${i}`}
                        className="mt-4 max-w-[65ch] border-l-2 border-navy/20 pl-4"
                      >
                        <blockquote className="font-body text-sm italic leading-relaxed text-navy/75">
                          {src.quote}
                        </blockquote>
                        <figcaption className="mt-2 text-xs font-body text-navy/50">
                          <span className="text-navy/70">{src.authority}</span>
                          <br />
                          {src.document_title}
                          {src.document_date ? `, ${src.document_date}` : ''}
                          {src.url && (
                            <>
                              {' '}
                              <a
                                href={src.url}
                                target="_blank"
                                rel="noreferrer nofollow"
                                className="text-cyan underline underline-offset-2 transition-colors hover:text-navy"
                              >
                                {t('rulesPage.openSource')}
                              </a>
                            </>
                          )}
                        </figcaption>
                      </figure>
                    ))}
                  </section>
                ))}
              </div>
            </section>

            {data.requirements.length > 0 && (
              <section id="documents" className="mt-14 scroll-mt-24">
                <h2 className="font-display text-2xl font-semibold tracking-tight text-navy">
                  {t('rulesPage.documentsTitle')}
                </h2>
                <p className="mt-1 max-w-[62ch] text-sm font-body text-navy/55">
                  {t('rulesPage.documentsHint')}
                </p>

                {/* A grid, not a spec table with a hairline under every row.
                    The number that matters is the lead time, so it is set as a
                    display figure rather than buried in a metadata line: it is
                    the one thing a reader cannot look up for themselves. */}
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {data.requirements.map((r) => (
                    <div
                      key={r.code}
                      className="rounded-field border border-navy/10 bg-white p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <p className="max-w-[34ch] font-display text-sm font-medium leading-snug text-navy">
                          {r.title}
                        </p>
                        {r.lead_time_days != null && r.lead_time_days > 0 && (
                          <p className="shrink-0 text-right">
                            <MonoText className="block text-2xl font-medium leading-none text-navy">
                              {r.lead_time_days}
                            </MonoText>
                            <MonoText className="block text-[10px] uppercase tracking-wide text-navy/40">
                              {t('rulesPage.daysUnit')}
                            </MonoText>
                          </p>
                        )}
                      </div>
                      <p className="mt-2 text-xs font-body leading-relaxed text-navy/55">
                        {r.issuer || t('rulesPage.issuerUnknown')}
                      </p>
                      {r.valid_for_days != null && (
                        <MonoText className="mt-1 block text-[11px] text-navy/45">
                          {t('rulesPage.validDays', { days: r.valid_for_days })}
                        </MonoText>
                      )}
                      {!r.is_mandatory && (
                        <MonoText className="mt-1 block text-[11px] text-navy/45">
                          {t('rulesPage.conditional')}
                        </MonoText>
                      )}
                      {r.notes && (
                        <p className="mt-2 text-xs font-body leading-relaxed text-navy/60">
                          {r.notes}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            <div className="mt-12 border-t border-navy/10 pt-6">
              {/* The same corridor as a file. `body` is stored as Markdown, so
                  this is the text itself rather than a conversion of it. A real
                  link, not a script-driven save: the URL works with `curl` and
                  survives being pasted to somebody else. */}
              <a
                href={`/api/rules/${data.category_key}/${data.direction}/${data.jurisdiction_code}/markdown?locale=${data.locale}`}
                className="text-sm font-display font-medium text-cyan transition-colors hover:text-navy"
              >
                {t('rulesPage.downloadMd')}
              </a>
              {/* §9.1 - what this page is and is not. Said once, plainly. */}
              <p className="mt-4 max-w-[65ch] text-xs font-body leading-relaxed text-navy/45">
                {t('rulesPage.disclaimer')}
              </p>
            </div>
          </div>

          {/* Contents. A map of a reference document, sticky where there is room
              for it and simply first-in-order where there is not. Hidden below
              `lg` rather than collapsed into an accordion: on a phone the page
              is one column and scrolling is the map. */}
          <nav
            aria-label={t('rulesPage.contents') as string}
            className="mt-12 hidden lg:sticky lg:top-24 lg:mt-0 lg:block lg:self-start"
          >
            <p className="font-display text-xs font-semibold uppercase tracking-[0.14em] text-navy/40">
              {t('rulesPage.contents')}
            </p>
            <ul className="mt-3 space-y-2 border-l border-navy/10 pl-3">
              {data.questions.length > 0 && (
                <li>
                  <a
                    href="#answers"
                    className="block text-xs font-body leading-snug text-navy/60 transition-colors hover:text-cyan"
                  >
                    {t('rulesPage.questionsTitle')}
                  </a>
                </li>
              )}
              {data.sections.map((s) => (
                <li key={`toc-${s.anchor}`}>
                  <a
                    href={`#${s.anchor}`}
                    className="block text-xs font-body leading-snug text-navy/60 transition-colors hover:text-cyan"
                  >
                    {s.title || s.anchor}
                  </a>
                </li>
              ))}
              {data.requirements.length > 0 && (
                <li>
                  <a
                    href="#documents"
                    className="block text-xs font-body leading-snug text-navy/60 transition-colors hover:text-cyan"
                  >
                    {t('rulesPage.documentsTitle')}
                  </a>
                </li>
              )}
            </ul>
          </nav>
        </div>
      </article>
    )
  }

  // `source="sender"` - somebody reading how to take a painting out of Russia
  // is a sender, and the waitlist entry should say so rather than pool every
  // rules reader under a fourth source that means nothing to whoever reads it.
  return (
    <LandingShell source="sender">
      {() => <div className="py-8 sm:py-12">{body()}</div>}
    </LandingShell>
  )
}
