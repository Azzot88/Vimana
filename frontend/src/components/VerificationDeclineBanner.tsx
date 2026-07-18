import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface Props {
  /** How the banner reads: sender was the one who got a polite decline
   *  from the carrier when they asked for the carrier's identity. */
  onRequestCollateral?: () => void
}

/** T_UX.1 / T2.1 pt.3 — banner shown to sender when carrier answered
 *  `declined_polite` to a verification request. Frames the decline as an
 *  intentional privacy choice by the carrier and offers an escalation path
 *  (larger deposit) instead of walking away.
 *
 *  Collateral CTA is a stub — real implementation lands with T5.x escrow.
 */
export default function VerificationDeclineBanner({ onRequestCollateral }: Props) {
  const { t } = useTranslation()
  const [modalOpen, setModalOpen] = useState(false)

  const handleClick = () => {
    if (onRequestCollateral) {
      onRequestCollateral()
    } else {
      setModalOpen(true)
    }
  }

  return (
    <div className="bg-amber/10 border border-amber/30 rounded-lg px-4 py-3 space-y-2">
      <p className="text-sm font-body text-navy">
        {t('verification.declinedPolite.senderCopy')}
      </p>
      <button
        type="button"
        onClick={handleClick}
        className="text-xs font-display font-medium text-amber hover:opacity-80"
      >
        {t('verification.declinedPolite.requestCollateralCTA')} →
      </button>

      {modalOpen && (
        <div
          className="fixed inset-0 bg-navy/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setModalOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl"
          >
            <h3 className="font-display font-semibold text-lg text-navy">
              {t('verification.declinedPolite.comingSoonTitle')}
            </h3>
            <p className="text-sm font-body text-navy/70">
              {t('verification.declinedPolite.comingSoonBody')}
            </p>
            <div className="flex justify-end">
              <button
                onClick={() => setModalOpen(false)}
                className="bg-navy text-ivory font-display font-medium px-4 py-2 rounded-lg text-sm hover:bg-navy-mid"
              >
                {t('common.close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
