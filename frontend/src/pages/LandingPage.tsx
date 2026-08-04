import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'
import LanguageSwitcher from '../components/LanguageSwitcher'
import MonoText from '../components/MonoText'
import Reveal from '../components/Reveal'
import { APP_VERSION } from '../version'

/**
 * T_UX.7 pt.2 — the landing, rebuilt in the reference's design language.
 *
 * What replaced what, and why:
 *
 * - **The 576-line `LP_CSS` string is gone.** It declared its own navy, its own
 *   three accents and its own paper colour, which is how the brand ended up
 *   existing four times. Everything here is a project token; there is no way to
 *   drift without editing `tailwind.config.js`, where drift is visible.
 * - **Density over air.** `VISUAL_DENSITY: 6`. The reference earns trust by
 *   putting facts close together, the way a boarding pass or a contract does.
 *   Doubling the whitespace would have made it look like every other SaaS page.
 * - **Mono for anything checkable.** Dates, codes, versions, counts. Prose in
 *   Inter, headings in Space Grotesk. That split is most of why the reference
 *   reads as a document rather than as marketing.
 * - **One accent.** Amber marks the four gates and the single primary action.
 *   Cyan appears only where something is live or verified. No third colour.
 *
 * Claims discipline (`DESIGNGUIDELINES §9.1`) is a *feature* of this page, not a
 * constraint on it: there is an explicit section for what does not exist yet,
 * and the version number is printed in the header. Nothing here says "soon",
 * because we do not have dates. Nothing counts members, because we have none to
 * count — the previous landing's investor-deck sibling did, and that number is
 * not ours to borrow.
 */

const GATES = ['post', 'match', 'handoff', 'release'] as const
const EVIDENCE = ['chain', 'identity', 'verification'] as const
const PENDING = ['payments', 'escrow', 'export'] as const

export default function LandingPage() {
  const { t } = useTranslation()
  const token = useAuthStore((s) => s.token)
  const nameRef = useRef<HTMLInputElement>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [successEmail, setSuccessEmail] = useState('')

  const isAuthed = !!token

  const openModal = () => {
    setModalOpen(true)
    setTimeout(() => nameRef.current?.focus(), 120)
  }

  const closeModal = () => {
    setModalOpen(false)
    setSubmitted(false)
    setSubmitError('')
  }

  // Field names and the request body are frozen (T_UX.7): the waitlist endpoint
  // and its admin read both depend on `{email, name, source}`.
  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const email = (form.elements.namedItem('email') as HTMLInputElement).value.trim()
    const name = (form.elements.namedItem('name') as HTMLInputElement).value.trim()
    setSubmitting(true)
    setSubmitError('')
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name, source: 'landing' }),
      })
      // 409 means the address is already on the list, which is success from the
      // visitor's side — they asked to be on it and they are.
      if (res.ok || res.status === 409) {
        setSuccessEmail(email)
        setSubmitted(true)
      } else {
        const detail = await res.json().catch(() => null)
        setSubmitError(detail?.detail || (t('landing.errorGeneric') as string))
      }
    } catch {
      setSubmitError(t('landing.errorNetwork') as string)
    } finally {
      setSubmitting(false)
    }
  }

  const Label = ({ children }: { children: React.ReactNode }) => (
    <MonoText className="text-[11px] uppercase tracking-[0.16em] text-muted">
      {children}
    </MonoText>
  )

  return (
    <div className="min-h-[100dvh] bg-ivory text-navy">
      <a href="#main" className="skip-link">
        {t('common.skipToContent')}
      </a>

      <nav className="sticky top-0 z-nav border-b border-navy/10 bg-ivory/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-5 py-3.5">
          <a href="/" className="font-display text-lg font-bold tracking-tight text-navy">
            Vimana<span className="text-amber">.</span>
          </a>
          {/* The version is read, never typed: the old header advertised
              v0.01.17 long after the build had moved on, which is the smallest
              possible version of the problem this whole page is about. */}
          <MonoText className="hidden text-[11px] tracking-[0.14em] text-muted sm:block">
            {t('landing.navTag', { version: APP_VERSION })}
          </MonoText>
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            {isAuthed ? (
              <Link
                to="/dashboard"
                className="rounded-field bg-navy px-4 py-2 font-display text-[13px] font-semibold text-ivory transition-colors hover:bg-navy-mid"
              >
                {t('landing.ctaDashboard')}
              </Link>
            ) : (
              <button
                type="button"
                onClick={openModal}
                className="rounded-field bg-navy px-4 py-2 font-display text-[13px] font-semibold text-ivory transition-colors hover:bg-navy-mid"
              >
                {t('landing.ctaInvite')}
              </button>
            )}
          </div>
        </div>
      </nav>

      <main id="main" className="mx-auto max-w-5xl px-5">
        {/* ── Hero ─────────────────────────────────────────────────────── */}
        {/* The hero is deliberately not wrapped in `Reveal`: it is on screen
            before anything can reveal it, and fading in content the visitor is
            already looking at is the motion equivalent of a splash screen. */}
        <section className="grid gap-10 border-b border-navy/10 py-14 md:grid-cols-[1.15fr_1fr] md:items-center md:py-20">
          <div>
            <Label>{t('landing.heroEyebrow')}</Label>
            <h1 className="mt-4 font-display text-[clamp(2.25rem,5.5vw,3.75rem)] font-bold leading-[1.03] tracking-[-0.03em] text-balance">
              {t('landing.heroTitle')}
            </h1>
            <p className="mt-5 max-w-[46ch] font-body text-[15px] leading-relaxed text-muted">
              {t('landing.heroSub')}
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              {!isAuthed && (
                <button
                  type="button"
                  onClick={openModal}
                  className="rounded-field bg-amber px-5 py-3 font-display text-sm font-semibold text-white transition-transform hover:brightness-95 active:translate-y-px"
                >
                  {t('landing.ctaInvite')}
                </button>
              )}
              <Link
                to="/trips"
                className="rounded-field border border-navy/20 px-5 py-3 font-display text-sm font-semibold text-navy transition-colors hover:bg-navy/5"
              >
                {t('landing.ctaBrowse')}
              </Link>
            </div>
          </div>

          {/* Boarding pass. Kept from the previous landing because it is the
              one image the product already owns: a parcel riding an existing
              flight is exactly what a boarding pass depicts. */}
          <div>
            <div className="rounded-card border border-navy/12 bg-white shadow-card">
              <div className="flex items-center justify-between border-b border-dashed border-navy/15 px-5 py-3">
                <MonoText className="text-[10px] uppercase tracking-[0.2em] text-muted">
                  {t('landing.boardingBrand')}
                </MonoText>
                <MonoText className="text-[10px] text-muted">VMN-2026-07841</MonoText>
              </div>
              <div className="flex items-end justify-between gap-4 px-5 py-5">
                <div>
                  <div className="font-display text-3xl font-bold leading-none tracking-tight">DXB</div>
                  <MonoText className="mt-1 text-[10px] text-muted">Dubai Intl</MonoText>
                </div>
                <div className="pb-2 text-amber" aria-hidden="true">✈</div>
                <div className="text-right">
                  <div className="font-display text-3xl font-bold leading-none tracking-tight">JFK</div>
                  <MonoText className="mt-1 text-[10px] text-muted">New York Kennedy</MonoText>
                </div>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-t border-navy/10 px-5 py-4">
                {[
                  ['boardingCarrier', 'Anastasia K.'],
                  ['boardingDeparts', '14 JUL · 02:35'],
                  ['boardingCargo', 'Document · 0.4 kg'],
                  ['boardingCapacity', '2.5 kg free'],
                ].map(([key, value]) => (
                  <div key={key}>
                    <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                      {t(`landing.${key}`)}
                    </dt>
                    <dd className="mt-0.5 font-mono text-[13px] text-navy">{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="flex items-center gap-2 border-t border-dashed border-navy/15 px-5 py-3">
                <span className="h-1.5 w-1.5 rounded-full bg-cyan" aria-hidden="true" />
                <MonoText className="text-[11px] text-muted">
                  {t('landing.boardingConfirmed')}
                </MonoText>
              </div>
            </div>
          </div>
        </section>

        {/* ── What is true today ───────────────────────────────────────── */}
        <section className="border-b border-navy/10 py-10">
          <Reveal>
            <Label>{t('landing.factsLabel')}</Label>
            <dl className="mt-5 grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
              {['chain', 'anchors', 'key', 'corridor'].map((key, i) => (
                <div key={key} className={i > 0 ? 'lg:border-l lg:border-navy/10 lg:pl-8' : undefined}>
                  <dt className="font-display text-2xl font-bold tracking-tight">
                    {t(`landing.fact.${key}.value`)}
                  </dt>
                  <dd className="mt-1 font-body text-[13px] leading-snug text-muted">
                    {t(`landing.fact.${key}.label`)}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </section>

        {/* ── Problem ──────────────────────────────────────────────────── */}
        <section className="grid gap-8 border-b border-navy/10 py-14 md:grid-cols-[0.9fr_1.1fr]">
          <Reveal>
            <Label>{t('landing.problemLabel')}</Label>
            <h2 className="mt-4 max-w-[18ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
              {t('landing.problemTitle')}
            </h2>
          </Reveal>
          <Reveal delay={0.08} className="space-y-4 font-body text-[15px] leading-relaxed text-muted">
            <p>{t('landing.problemBody1')}</p>
            <p>{t('landing.problemBody2')}</p>
          </Reveal>
        </section>

        {/* ── Four gates ───────────────────────────────────────────────── */}
        <section className="border-b border-navy/10 py-14">
          <Reveal>
            <Label>{t('landing.gatesLabel')}</Label>
            <h2 className="mt-4 max-w-[22ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
              {t('landing.gatesTitle')}
            </h2>
          </Reveal>
          <ol className="mt-9 grid gap-px overflow-hidden rounded-card border border-navy/10 bg-navy/10 sm:grid-cols-2 lg:grid-cols-4">
            {GATES.map((gate, i) => (
              <Reveal key={gate} delay={i * 0.06} className="bg-ivory">
                <li className="h-full p-6">
                  <MonoText className="text-[13px] font-medium text-amber">
                    {String(i + 1).padStart(2, '0')}
                  </MonoText>
                  <h3 className="mt-3 font-display text-lg font-semibold tracking-tight">
                    {t(`landing.gate.${gate}.title`)}
                  </h3>
                  <p className="mt-2 font-body text-[13.5px] leading-relaxed text-muted">
                    {t(`landing.gate.${gate}.body`)}
                  </p>
                </li>
              </Reveal>
            ))}
          </ol>
        </section>

        {/* ── What holds it together ───────────────────────────────────── */}
        <section className="border-b border-navy/10 py-14">
          <Reveal>
            <Label>{t('landing.evidenceLabel')}</Label>
            <h2 className="mt-4 max-w-[24ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
              {t('landing.evidenceTitle')}
            </h2>
          </Reveal>
          <div className="mt-9 space-y-px overflow-hidden rounded-card border border-navy/10 bg-navy/10">
            {EVIDENCE.map((item, i) => (
              <Reveal key={item} delay={i * 0.06} className="bg-white">
                <article className="grid gap-3 p-6 md:grid-cols-[0.8fr_1.2fr] md:gap-8">
                  <h3 className="font-display text-lg font-semibold tracking-tight">
                    {t(`landing.evidence.${item}.title`)}
                  </h3>
                  <div className="space-y-2">
                    <p className="font-body text-[14px] leading-relaxed text-muted">
                      {t(`landing.evidence.${item}.body`)}
                    </p>
                    {/* The limit of the claim, printed next to the claim. This
                        is the §9.1 rule made visible rather than obeyed
                        quietly: a reader who only skims the bold line still
                        cannot come away with more than the mechanism gives. */}
                    <MonoText className="block text-[11.5px] leading-relaxed text-muted">
                      {t(`landing.evidence.${item}.limit`)}
                    </MonoText>
                  </div>
                </article>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ── Not built yet ────────────────────────────────────────────── */}
        <section className="border-b border-navy/10 py-14">
          <Reveal>
            <Label>{t('landing.pendingLabel')}</Label>
            <h2 className="mt-4 max-w-[20ch] font-display text-[clamp(1.6rem,3.2vw,2.25rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
              {t('landing.pendingTitle')}
            </h2>
            <p className="mt-4 max-w-[54ch] font-body text-[15px] leading-relaxed text-muted">
              {t('landing.pendingBody')}
            </p>
          </Reveal>
          <ul className="mt-8 grid gap-4 sm:grid-cols-3">
            {PENDING.map((item, i) => (
              <Reveal key={item} delay={i * 0.06}>
                <li className="h-full rounded-card border border-dashed border-navy/20 p-5">
                  <MonoText className="text-[11px] uppercase tracking-[0.14em] text-muted">
                    {t('landing.pendingTag')}
                  </MonoText>
                  <h3 className="mt-2.5 font-display text-base font-semibold tracking-tight text-navy/80">
                    {t(`landing.pending.${item}.title`)}
                  </h3>
                  <p className="mt-1.5 font-body text-[13px] leading-relaxed text-muted">
                    {t(`landing.pending.${item}.body`)}
                  </p>
                </li>
              </Reveal>
            ))}
          </ul>
        </section>

        {/* ── Closing ──────────────────────────────────────────────────── */}
        <section className="py-16">
          <Reveal className="rounded-card border border-navy/12 bg-navy px-7 py-10 text-ivory md:px-12 md:py-14">
            <MonoText className="text-[11px] uppercase tracking-[0.16em] text-ivory/70">
              {t('landing.closingLabel')}
            </MonoText>
            <h2 className="mt-4 max-w-[20ch] font-display text-[clamp(1.6rem,3.4vw,2.5rem)] font-bold leading-tight tracking-[-0.02em] text-balance">
              {t('landing.closingTitle')}
            </h2>
            <p className="mt-4 max-w-[48ch] font-body text-[15px] leading-relaxed text-ivory/70">
              {t('landing.closingBody')}
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              {isAuthed ? (
                <Link
                  to="/dashboard"
                  className="rounded-field bg-amber px-5 py-3 font-display text-sm font-semibold text-white transition-transform hover:brightness-95 active:translate-y-px"
                >
                  {t('landing.ctaDashboard')}
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={openModal}
                  className="rounded-field bg-amber px-5 py-3 font-display text-sm font-semibold text-white transition-transform hover:brightness-95 active:translate-y-px"
                >
                  {t('landing.ctaInvite')}
                </button>
              )}
              <Link
                to="/login"
                className="rounded-field border border-ivory/25 px-5 py-3 font-display text-sm font-semibold text-ivory transition-colors hover:bg-ivory/10"
              >
                {t('landing.ctaLogin')}
              </Link>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="border-t border-navy/10">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-6">
          <MonoText className="text-[11px] uppercase tracking-[0.14em] text-muted">
            Vimana · {t('landing.footerTagline')}
          </MonoText>
          <MonoText className="text-[11px] text-muted">
            {t('landing.navTag', { version: APP_VERSION })}
          </MonoText>
        </div>
      </footer>

      {modalOpen && (
        <div
          className="fixed inset-0 z-modal flex items-center justify-center bg-navy/50 px-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeModal()
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="waitlist-title"
            className="w-full max-w-md rounded-card border border-navy/10 bg-white p-6 shadow-lift"
          >
            {submitted ? (
              <div className="space-y-3">
                <h2 id="waitlist-title" className="font-display text-xl font-bold tracking-tight">
                  {t('landing.modalSuccessTitle')}
                </h2>
                <p className="font-body text-sm leading-relaxed text-muted">
                  {t('landing.modalSuccessText', { email: successEmail })}
                </p>
                <button
                  type="button"
                  onClick={closeModal}
                  className="mt-2 w-full rounded-field border border-navy/20 py-2.5 font-body text-sm text-navy transition-colors hover:bg-navy/5"
                >
                  {t('common.close')}
                </button>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-4">
                  <h2 id="waitlist-title" className="font-display text-xl font-bold tracking-tight">
                    {t('landing.modalTitle')}
                  </h2>
                  <button
                    type="button"
                    onClick={closeModal}
                    aria-label={t('common.close') as string}
                    className="-mr-1 -mt-1 rounded-field px-2 py-1 text-muted transition-colors hover:bg-navy/5 hover:text-navy"
                  >
                    ×
                  </button>
                </div>
                <p className="mt-2 font-body text-sm leading-relaxed text-muted">
                  {t('landing.modalSub')}
                </p>
                <form onSubmit={handleSubmit} className="mt-5 space-y-3">
                  <div>
                    <label
                      htmlFor="waitlist-name"
                      className="mb-1 block font-mono text-[11px] uppercase tracking-[0.12em] text-muted"
                    >
                      {t('landing.modalName')}
                    </label>
                    <input
                      ref={nameRef}
                      id="waitlist-name"
                      name="name"
                      type="text"
                      autoComplete="name"
                      className="w-full rounded-field border border-navy/20 px-3 py-2.5 font-body text-sm text-navy"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="waitlist-email"
                      className="mb-1 block font-mono text-[11px] uppercase tracking-[0.12em] text-muted"
                    >
                      {t('landing.modalEmail')}
                    </label>
                    <input
                      id="waitlist-email"
                      name="email"
                      type="email"
                      required
                      autoComplete="email"
                      className="w-full rounded-field border border-navy/20 px-3 py-2.5 font-body text-sm text-navy"
                    />
                  </div>
                  {submitError && (
                    <p className="font-mono text-xs text-danger">{submitError}</p>
                  )}
                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full rounded-field bg-navy py-3 font-display text-sm font-semibold text-ivory transition-colors hover:bg-navy-mid disabled:opacity-50"
                  >
                    {submitting ? t('common.sending') : t('landing.modalSubmit')}
                  </button>
                </form>
                <p className="mt-3 font-body text-[11.5px] leading-relaxed text-muted">
                  {t('landing.modalFine')}
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
