import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import MonoText from '../MonoText'
import Reveal from '../Reveal'
import FlowStrip from './FlowStrip'
import LandingShell, { LandingLabel, type WaitlistSource } from './LandingShell'

/**
 * T_UX.23 — one skeleton, three audiences.
 *
 * The brief set the ratio explicitly: **70% shared design, 30% visual
 * difference — but 30% shared UX and 70% different content and actions.** That
 * is a component, not three files: the shape, rhythm, type scale and section
 * order are written once here, and everything a visitor actually reads comes
 * from `audience.<key>.*` in the locale files.
 *
 * Structure, in the order a stranger reads it:
 *   hero → the flow in four words → the same four as real steps →
 *   what is not built yet → closing call.
 *
 * The fourth section is not padding and not modesty. `DESIGNGUIDELINES §9.1`
 * forbids a page from claiming more than the mechanism under it delivers, and
 * these three pages are the most tempting place in the product to break that:
 * an audience page exists to sell. Printing the limit in the same type size as
 * the promise is how the rule stays kept when the copy is rewritten later.
 */

interface Props {
  /** Key under `audience.*` in the locales, and the waitlist `source`. */
  audience: Extract<WaitlistSource, 'carrier' | 'sender' | 'business'>
  /** Where the secondary button goes — the audience next door. */
  secondaryTo: string
}

const STEP_KEYS = ['1', '2', '3', '4'] as const

export default function AudienceLanding({ audience, secondaryTo }: Props) {
  const { t } = useTranslation()
  const k = (suffix: string) => `audience.${audience}.${suffix}`

  return (
    <LandingShell source={audience} navCtaKey={k('ctaPrimary')}>
      {(openWaitlist) => (
        <>
          {/* ── Hero ─────────────────────────────────────────────────────
              Not wrapped in `Reveal`: it is on screen before anything can
              reveal it, and fading in content the visitor is already looking
              at is the motion equivalent of a splash screen. */}
          <section className="border-b border-navy/10 py-14 md:py-20">
            <LandingLabel>{t(k('eyebrow'))}</LandingLabel>
            <h1 className="mt-4 max-w-[20ch] font-display text-[clamp(2.25rem,5.5vw,3.75rem)] font-bold leading-[1.03] tracking-[-0.03em] text-balance">
              {t(k('title'))}
            </h1>
            <p className="mt-5 max-w-[52ch] font-body text-[15px] leading-relaxed text-navy/70">
              {t(k('sub'))}
            </p>

            <div className="mt-8 max-w-[46rem]">
              <FlowStrip
                steps={STEP_KEYS.map((n) => t(k(`flow.${n}`)) as string)}
              />
            </div>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={openWaitlist}
                className="rounded-field bg-amber px-5 py-3 font-display text-sm font-semibold text-white transition-transform hover:brightness-95 active:translate-y-px"
              >
                {t(k('ctaPrimary'))}
              </button>
              <Link
                to={secondaryTo}
                className="rounded-field border border-navy/20 px-5 py-3 font-display text-sm font-semibold text-navy transition-colors hover:bg-navy/5"
              >
                {t(k('ctaSecondary'))}
              </Link>
            </div>
          </section>

          {/* ── The four steps, spelled out ──────────────────────────────── */}
          <section className="border-b border-navy/10 py-14">
            <Reveal>
              <LandingLabel>{t(k('stepsLabel'))}</LandingLabel>
              <h2 className="mt-4 max-w-[22ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t(k('stepsTitle'))}
              </h2>
            </Reveal>
            <ol className="mt-9 grid gap-px overflow-hidden rounded-card border border-navy/10 bg-navy/10 sm:grid-cols-2 lg:grid-cols-4">
              {STEP_KEYS.map((n, i) => (
                <Reveal key={n} as="li" delay={i * 0.06} className="h-full bg-ivory p-6">
                  <div>
                    <MonoText className="text-[13px] font-medium text-amber">
                      {String(i + 1).padStart(2, '0')}
                    </MonoText>
                    <h3 className="mt-3 font-display text-lg font-semibold tracking-tight">
                      {t(k(`step.${n}.title`))}
                    </h3>
                    <p className="mt-2 font-body text-[13.5px] leading-relaxed text-navy/65">
                      {t(k(`step.${n}.body`))}
                    </p>
                  </div>
                </Reveal>
              ))}
            </ol>
          </section>

          {/* ── The limit, printed as loudly as the promise ──────────────── */}
          <section className="border-b border-navy/10 py-14">
            <Reveal>
              <LandingLabel>{t(k('limitsLabel'))}</LandingLabel>
              <h2 className="mt-4 max-w-[24ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t(k('limitsTitle'))}
              </h2>
              <p className="mt-4 max-w-[58ch] font-body text-[15px] leading-relaxed text-navy/70">
                {t(k('limitsBody'))}
              </p>
            </Reveal>
          </section>

          {/* ── Closing ─────────────────────────────────────────────────── */}
          <section className="py-16">
            <Reveal className="rounded-card border border-navy/12 bg-navy px-7 py-10 text-ivory md:px-12 md:py-14">
              <MonoText className="text-[11px] uppercase tracking-[0.16em] text-ivory/45">
                {t('landing.closingLabel')}
              </MonoText>
              <h2 className="mt-4 max-w-[20ch] font-display text-[clamp(1.6rem,3.4vw,2.5rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
                {t(k('closingTitle'))}
              </h2>
              <p className="mt-4 max-w-[48ch] font-body text-[15px] leading-relaxed text-ivory/70">
                {t(k('closingBody'))}
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={openWaitlist}
                  className="rounded-field bg-amber px-5 py-3 font-display text-sm font-semibold text-white transition-transform hover:brightness-95 active:translate-y-px"
                >
                  {t(k('ctaPrimary'))}
                </button>
                <Link
                  to="/login"
                  className="rounded-field border border-ivory/25 px-5 py-3 font-display text-sm font-semibold text-ivory transition-colors hover:bg-ivory/10"
                >
                  {t('landing.ctaLogin')}
                </Link>
              </div>
            </Reveal>
          </section>
        </>
      )}
    </LandingShell>
  )
}
