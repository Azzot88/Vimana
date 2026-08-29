import { useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../../stores/auth'
import LanguageSwitcher from '../LanguageSwitcher'
import MonoText from '../MonoText'
import { APP_VERSION } from '../../version'

/**
 * T_UX.23 — the frame every public page shares: header, footer, waitlist.
 *
 * The split into `/`, `/carrier`, `/send` and `/business` is **70% shared
 * design, 30% different** — so the parts that carry "you are still on the same
 * platform" live here once and cannot drift: logo, version tag, language
 * switcher, primary button shape, footer, and the waitlist dialog itself.
 * What differs between audiences is content and actions, and that lives in the
 * pages.
 *
 * The dialog is passed down as a function rather than duplicated: three pages
 * needed the same form with a different `source`, and a third copy of a form
 * that posts to `/api/waitlist` is how field names quietly stop matching.
 */

/** Frozen with the endpoint and its admin read (T_UX.7): `{email, name, source}`. */
export type WaitlistSource = 'landing' | 'carrier' | 'sender' | 'business'

interface Props {
  source: WaitlistSource
  /** Nav button for a guest. Signed-in visitors always get "go to the panel". */
  navCtaKey?: string
  children: (openWaitlist: () => void) => ReactNode
}

export function LandingLabel({ children }: { children: ReactNode }) {
  return (
    <MonoText className="text-[11px] uppercase tracking-[0.16em] text-navy/40">
      {children}
    </MonoText>
  )
}

export default function LandingShell({
  source,
  navCtaKey = 'landing.ctaInvite',
  children,
}: Props) {
  const { t, i18n } = useTranslation()
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const nameRef = useRef<HTMLInputElement>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [successEmail, setSuccessEmail] = useState('')

  const isAuthed = !!token
  // Where "go to the panel" leads now that the panel has two addresses. Falls
  // back to the carrier side only when the user is not loaded yet — `/send` is
  // the safer guess for nobody in particular, since every account can send.
  const panelHref = user?.active_mode === 'carrier' ? '/carrier' : '/send'

  const openWaitlist = () => {
    setModalOpen(true)
    setTimeout(() => nameRef.current?.focus(), 120)
  }

  const closeModal = () => {
    setModalOpen(false)
    setSubmitted(false)
    setSubmitError('')
  }

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
        // T_UX.9 — the language the visitor is reading right now, so the
        // confirmation letter arrives in it instead of guessing English.
        // T_UX.23 — `source` now says *which* page asked, which is the only way
        // to tell a carrier request from a business one before anyone replies.
        body: JSON.stringify({ email, name, source, locale: i18n.language }),
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

  return (
    <div className="min-h-[100dvh] bg-ivory text-navy">
      <a href="#main" className="skip-link">
        {t('common.skipToContent')}
      </a>

      <nav className="sticky top-0 z-nav border-b border-navy/10 bg-ivory/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-5 py-3.5">
          <Link to="/" className="font-display text-lg font-bold tracking-tight text-navy">
            Vimana<span className="text-amber">.</span>
          </Link>
          {/* The version is read, never typed: the old header advertised
              v0.01.17 long after the build had moved on, which is the smallest
              possible version of the problem this whole page is about. */}
          <MonoText className="hidden text-[11px] tracking-[0.14em] text-navy/40 sm:block">
            {t('landing.navTag', { version: APP_VERSION })}
          </MonoText>
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            {isAuthed ? (
              <Link
                to={panelHref}
                className="rounded-field bg-navy px-4 py-2 font-display text-[13px] font-semibold text-ivory transition-colors hover:bg-navy-mid"
              >
                {t('landing.ctaDashboard')}
              </Link>
            ) : (
              <button
                type="button"
                onClick={openWaitlist}
                className="rounded-field bg-navy px-4 py-2 font-display text-[13px] font-semibold text-ivory transition-colors hover:bg-navy-mid"
              >
                {t(navCtaKey)}
              </button>
            )}
          </div>
        </div>
      </nav>

      <main id="main" className="mx-auto max-w-5xl px-5">
        {children(openWaitlist)}
      </main>

      <footer className="border-t border-navy/10">
        <div className="mx-auto max-w-5xl px-5 py-6">
          {/* T_UX.23 — the three audiences link to each other from every page.
              Somebody who arrived on the wrong one should not have to guess
              that the right one exists, and a footer is where a reader who did
              not find what they came for actually looks. */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 font-body text-[13px]">
            <Link to="/carrier" className="text-navy/60 transition-colors hover:text-navy">
              {t('audience.carrier.navLink')}
            </Link>
            <Link to="/send" className="text-navy/60 transition-colors hover:text-navy">
              {t('audience.sender.navLink')}
            </Link>
            <Link to="/business" className="text-navy/60 transition-colors hover:text-navy">
              {t('audience.business.navLink')}
            </Link>
            {/* T3.11.03 — the directory's only entry point on the site. It was
                reachable by typing its address and by nothing else: the top of
                the funnel with nothing pointing at it. In the footer rather
                than the header on purpose — it is what a reader looks for after
                the page has not answered them, which is what a footer is. */}
            <Link to="/rules" className="text-navy/60 transition-colors hover:text-navy">
              {t('rulesIndex.navLink')}
            </Link>
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-navy/10 pt-4">
            <MonoText className="text-[11px] uppercase tracking-[0.14em] text-navy/40">
              Vimana · {t('landing.footerTagline')}
            </MonoText>
            <MonoText className="text-[11px] text-navy/35">
              {t('landing.navTag', { version: APP_VERSION })}
            </MonoText>
          </div>
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
                <p className="font-body text-sm leading-relaxed text-navy/70">
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
                  {/* Only business gets its own wording. A company is not
                      asking for a beta invite, it is asking to talk — and the
                      other three audiences are asking for exactly the same
                      thing as each other, so three copies of one sentence
                      would be three places to keep in step for nothing. */}
                  <h2 id="waitlist-title" className="font-display text-xl font-bold tracking-tight">
                    {t(source === 'business' ? 'landing.modalTitleBusiness' : 'landing.modalTitle')}
                  </h2>
                  <button
                    type="button"
                    onClick={closeModal}
                    aria-label={t('common.close') as string}
                    className="-mr-1 -mt-1 rounded-field px-2 py-1 text-navy/40 transition-colors hover:bg-navy/5 hover:text-navy"
                  >
                    ×
                  </button>
                </div>
                <p className="mt-2 font-body text-sm leading-relaxed text-navy/65">
                  {t(source === 'business' ? 'landing.modalSubBusiness' : 'landing.modalSub')}
                </p>
                <form onSubmit={handleSubmit} className="mt-5 space-y-3">
                  <div>
                    <label
                      htmlFor="waitlist-name"
                      className="mb-1 block font-mono text-[11px] uppercase tracking-[0.12em] text-navy/45"
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
                      className="mb-1 block font-mono text-[11px] uppercase tracking-[0.12em] text-navy/45"
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
                <p className="mt-3 font-body text-[11.5px] leading-relaxed text-navy/45">
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
