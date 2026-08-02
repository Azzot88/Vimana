import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getKeypairStatus,
  markArchiveNoticeSeen,
  setArchiveChoice,
  type KeypairStatus,
} from '../api/keypair'
import { useAuthStore } from '../stores/auth'

/**
 * T3.19 — what a retired identity is told, and the one choice it still has.
 *
 * Two surfaces, and the split is the point:
 *
 * - **A modal, once.** The first sign-in after the key is gone is the only
 *   moment the explanation is news. A permanent dialog over a state that will
 *   never change is nagging, and gets closed unread by the third time — which
 *   would cost exactly the people who needed to read it.
 * - **A banner, always.** The state does not change back, so hiding the banner
 *   after a while would mean the account quietly stops saying what it is.
 *
 * Closing the modal is not an answer. It records that the notice was shown and
 * leaves the choice null, which is the default the notice just described.
 * Consent taken from a close button is not consent.
 *
 * The window and its asymmetry are stated out loud rather than implied: doing
 * nothing leaves the page open, saying no closes it for good. Whoever lost both
 * the key and their access never sees this at all and gets the default — that
 * follows from the rule, and it is said here instead of being left to be
 * discovered.
 */
export default function ArchiveNotice() {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [status, setStatus] = useState<KeypairStatus | null>(null)
  const [open, setOpen] = useState(false)
  const [confirmingHide, setConfirmingHide] = useState(false)
  const [understood, setUnderstood] = useState(false)
  const [busy, setBusy] = useState(false)

  const retired = Boolean(user?.key_lost)

  useEffect(() => {
    // No request at all for a live identity — the `/me` payload already
    // answered the only question that decides whether this component matters.
    if (!retired) return
    getKeypairStatus()
      .then(({ data }) => {
        setStatus(data)
        setOpen(data.archive_notice_seen_at === null)
      })
      .catch(() => {})
  }, [retired])

  if (!retired || !status) return null

  const windowEnds = status.archive_window_ends_at
  const windowOpen = windowEnds !== null && new Date(windowEnds) > new Date()
  const deadline = windowEnds
    ? new Date(windowEnds).toLocaleDateString(i18n.language)
    : ''
  const closed = status.archive_choice === 'hide'

  const dismiss = async () => {
    setOpen(false)
    setConfirmingHide(false)
    setUnderstood(false)
    if (status.archive_notice_seen_at !== null) return
    try {
      const { data } = await markArchiveNoticeSeen()
      setStatus(data)
    } catch { /* silent — the modal reappears next time, which is the safe way to fail */ }
  }

  const choose = async (choice: 'show' | 'hide') => {
    setBusy(true)
    try {
      const { data } = await setArchiveChoice(choice)
      setStatus(data)
      setOpen(false)
      setConfirmingHide(false)
      setUnderstood(false)
    } catch { /* silent — the banner keeps showing the unchanged state */ }
    finally { setBusy(false) }
  }

  return (
    <>
      <div
        data-testid="archive-banner"
        data-state={closed ? 'closed' : windowOpen && !status.archive_choice ? 'undecided' : 'open'}
        className="bg-navy/5 border border-navy/15 rounded-xl px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-1"
      >
        <p className="text-sm font-body text-navy flex-1 min-w-[12rem]">
          <span className="font-medium">{t('archive.bannerTitle')}</span>{' '}
          {closed
            ? t('archive.bannerClosed')
            : windowOpen && !status.archive_choice
              ? t('archive.bannerUndecided', { date: deadline })
              : t('archive.bannerOpen')}
        </p>
        {!closed && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            data-testid="archive-banner-cta"
            className="text-sm font-body font-medium text-navy underline underline-offset-2"
          >
            {t('archive.bannerCta')}
          </button>
        )}
      </div>

      {open && (
        <div className="fixed inset-0 bg-navy/40 flex items-center justify-center px-4 z-50">
          <div
            data-testid="archive-modal"
            className="bg-white rounded-2xl border border-navy/10 p-5 w-full max-w-md space-y-4 max-h-[90vh] overflow-y-auto"
          >
            <h3 className="font-display font-semibold text-lg text-navy">
              {t('archive.modalTitle')}
            </h3>

            {/* What happened · what remains · what now. In that order, because
                that is the order the questions arrive in. */}
            <p className="text-sm font-body text-navy/70">{t('archive.modalWhat')}</p>
            <p className="text-sm font-body text-navy/70">{t('archive.modalRemains')}</p>

            <div className="bg-navy/5 rounded-lg px-3 py-2 space-y-1">
              <p className="text-sm font-body text-navy/70">
                {windowOpen
                  ? t('archive.modalWindow', { date: deadline })
                  : t('archive.modalWindowClosed')}
              </p>
              {/* Said plainly rather than discovered later: someone who lost
                  their access too will never read this, and the default applies
                  to them anyway. */}
              <p className="text-xs font-body text-navy/50">{t('archive.modalNoAccess')}</p>
            </div>

            {windowOpen && !confirmingHide && (
              <div className="space-y-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void choose('show')}
                  data-testid="archive-choose-show"
                  className="w-full bg-navy text-ivory rounded-lg py-2.5 text-sm font-body disabled:opacity-50"
                >
                  {t('archive.keepOpen')}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingHide(true)}
                  data-testid="archive-choose-hide"
                  className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
                >
                  {t('archive.closePage')}
                </button>
                <button
                  type="button"
                  onClick={() => void dismiss()}
                  data-testid="archive-decide-later"
                  className="w-full text-sm font-body text-navy/50 py-1"
                >
                  {t('archive.decideLater')}
                </button>
              </div>
            )}

            {windowOpen && confirmingHide && (
              <div className="space-y-3">
                {/* "Cremation" is not the word and must never be: nothing is
                    destroyed. The chain, the signatures and the deal history
                    stay — half that record belongs to the counterparty. What
                    closes is the display. */}
                <p className="text-sm font-body text-navy/70">
                  {t('archive.hideConsequences')}
                </p>
                <label className="flex items-start gap-2 text-sm font-body text-navy/70">
                  <input
                    type="checkbox"
                    checked={understood}
                    onChange={(e) => setUnderstood(e.target.checked)}
                    data-testid="archive-hide-understood"
                    className="mt-1"
                  />
                  <span>{t('archive.hideUnderstood')}</span>
                </label>
                <button
                  type="button"
                  disabled={!understood || busy}
                  onClick={() => void choose('hide')}
                  data-testid="archive-hide-confirm"
                  className="w-full bg-navy text-ivory rounded-lg py-2.5 text-sm font-body disabled:opacity-40"
                >
                  {t('archive.hideConfirm')}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingHide(false)}
                  className="w-full text-sm font-body text-navy/50 py-1"
                >
                  {t('common.cancel')}
                </button>
              </div>
            )}

            {!windowOpen && (
              <button
                type="button"
                onClick={() => void dismiss()}
                className="w-full border border-navy/20 rounded-lg py-2.5 text-sm font-body text-navy"
              >
                {t('common.close')}
              </button>
            )}
          </div>
        </div>
      )}
    </>
  )
}
