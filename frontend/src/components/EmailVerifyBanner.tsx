import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { listDeals } from '../api/deals'
import { useAuthStore } from '../stores/auth'

/**
 * Everything this product says about the email channel, in one place.
 *
 * Two states, never both:
 *
 * 1. **T3.11** — an address was claimed but never proven. Nothing is gated by
 *    it; what is uncertain is whether the channel works at all.
 * 2. **T3.17** — no address at all, *and* the account has started a deal.
 *    Only then is there something to lose: recovery and deal notifications
 *    both ride on that channel. At registration we say nothing — a warning
 *    from day one teaches people to ignore banners by the time one matters.
 *
 * The second is dismissible and stays dismissed: it is advice, not a blocker.
 * Amber, not red — attention, not danger (DESIGNGUIDELINES: red is reserved).
 */
const DISMISS_KEY = 'banner:add-email:dismissed'

export default function EmailVerifyBanner() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const [hasDeals, setHasDeals] = useState(false)
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === '1',
  )

  const needsAddress = Boolean(user && !user.email)

  useEffect(() => {
    if (!needsAddress || dismissed) return
    // One request, and only for an account that has no address at all — the
    // condition is "has something to lose", and only the deals list knows.
    listDeals({ limit: 1 })
      .then(({ data }) => setHasDeals(data.items.length > 0))
      .catch(() => {})
  }, [needsAddress, dismissed])

  if (!user) return null

  if (needsAddress) {
    if (dismissed || !hasDeals) return null
    return (
      <div className="bg-amber/10 border border-amber/40 rounded-xl px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="text-sm font-body text-navy flex-1 min-w-[12rem]">
          {t('verifyEmail.addBannerBody')}
        </p>
        <Link
          to="/profile/keys"
          className="text-sm font-body font-medium text-navy underline underline-offset-2"
        >
          {t('verifyEmail.addBannerCta')}
        </Link>
        <button
          type="button"
          onClick={() => {
            localStorage.setItem(DISMISS_KEY, '1')
            setDismissed(true)
          }}
          className="text-sm font-body text-navy/50"
        >
          {t('common.cancel')}
        </button>
      </div>
    )
  }

  if (user.email_verified) return null

  return (
    <div className="bg-amber/10 border border-amber/40 rounded-xl px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-1">
      <p className="text-sm font-body text-navy flex-1 min-w-[12rem]">
        {t('verifyEmail.bannerBody')}
      </p>
      <Link
        to="/verify-email"
        className="text-sm font-body font-medium text-navy underline underline-offset-2"
      >
        {t('verifyEmail.bannerCta')}
      </Link>
    </div>
  )
}
