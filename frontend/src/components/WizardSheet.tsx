import { useEffect, useRef, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * T3.11.20 — the shell every step of the trip wizard sits in.
 *
 * On a phone it is a sheet that owns the screen; on a wide viewport a centred
 * card. That is not a preference: a centred dialog holding a form of eight
 * fields is where mobile keyboards cause the damage — the browser zooms to the
 * focused input, the dialog is taller than the visible area, and the field
 * being typed into scrolls out from under the thumb.
 *
 * Height is `100dvh`, not `100vh`. With `vh` the mobile address bar is counted
 * as visible, the sheet ends up taller than the screen, and the footer holding
 * "Next" sits permanently below the fold.
 *
 * The footer is in the flow, not `position: fixed`. A fixed footer is pushed
 * under the on-screen keyboard on both iOS and Android; a flex column with a
 * scrolling body keeps it at the bottom of what is actually visible.
 *
 * Functions (PROJECT §6.2a):
 * - `WizardSheet(props)` — default export.
 *   Called by: `pages/NewTripPage`.
 */
interface Props {
  /** 1-based. Drives the progress bar and the spoken position. */
  step: number
  total: number
  title: string
  /** One line under the title saying what this step buys the carrier. */
  subtitle?: string
  /** Absent on the first step, where there is nothing to go back to. */
  onBack?: () => void
  onClose: () => void
  children: ReactNode
  /** Buttons. Owned by the caller: which of them exist is a product decision
   *  per step, not a property of the shell. */
  footer: ReactNode
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

export default function WizardSheet({
  step,
  total,
  title,
  subtitle,
  onBack,
  onClose,
  children,
  footer,
}: Props) {
  const { t } = useTranslation()
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = 'wizard-title'

  // The page behind must not scroll while the sheet is open — on a phone it is
  // the difference between a sheet and a sheet with the feed sliding under it.
  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  // Focus moves into the sheet on open and is restored to whatever opened it on
  // close. Without the restore, closing drops the caret at the top of the
  // document and a keyboard user starts the page again from nothing.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    panelRef.current?.focus()
    return () => opener?.focus?.()
  }, [])

  // Focus stays inside while it is open. `aria-modal` tells a screen reader the
  // rest is inert; it does nothing at all for the Tab key.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key !== 'Tab') return
      const panel = panelRef.current
      if (!panel) return
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || active === panel)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-modal bg-navy/60 backdrop-blur-sm flex items-end sm:items-center justify-center sm:p-4">
      {/* No dismiss-on-backdrop. A form with a saved draft behind it is not
          something to lose to a stray tap next to the sheet; leaving is the
          cross, which asks. */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="bg-white w-full h-[100dvh] sm:h-auto sm:max-h-[90dvh] sm:max-w-2xl sm:rounded-card flex flex-col focus:outline-none"
      >
        <div className="px-4 sm:px-6 pt-4 pb-3 space-y-3 border-b border-navy/10">
          <div className="flex items-center justify-between gap-3 min-h-[2.75rem]">
            {onBack ? (
              <button
                type="button"
                onClick={onBack}
                className="text-sm font-body text-navy/60 hover:text-navy transition-colors px-2 py-2 -ml-2 min-h-[2.75rem]"
              >
                ← {t('common.back')}
              </button>
            ) : (
              <span />
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label={t('common.close') as string}
              className="text-navy/40 hover:text-navy transition-colors px-2 py-2 -mr-2 min-h-[2.75rem] text-lg"
            >
              ×
            </button>
          </div>

          {/* Drawn, not written. The spoken position lives in the label, so a
              screen reader still hears "step 2 of 4" without the sighted
              reader being told twice. */}
          <div
            role="progressbar"
            aria-valuemin={1}
            aria-valuemax={total}
            aria-valuenow={step}
            aria-label={t('trips.wizard.progress', { step, total }) as string}
            className="flex gap-1.5"
          >
            {Array.from({ length: total }, (_, i) => (
              <span
                key={i}
                className={`h-1 flex-1 rounded-full transition-colors ${
                  i < step ? 'bg-cyan' : 'bg-navy/10'
                }`}
              />
            ))}
          </div>

          <div>
            <h2
              id={titleId}
              className="font-display font-bold text-xl text-navy"
            >
              {title}
            </h2>
            {subtitle && (
              <p className="text-xs font-body text-navy/50 mt-0.5">{subtitle}</p>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
          {children}
        </div>

        <div
          className="px-4 sm:px-6 py-3 border-t border-navy/10 flex flex-wrap gap-2 justify-end"
          style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}
        >
          {footer}
        </div>
      </div>
    </div>
  )
}
