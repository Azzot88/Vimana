import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../stores/auth'

/** T3.11 — nudge for an email that was claimed but never proven.
 *
 *  Deliberately absent for an account with no email at all: nothing was
 *  claimed, so nothing is pending. Amber, not red — this is "attention", not
 *  "danger" (DESIGNGUIDELINES: red is reserved).
 */
export default function EmailVerifyBanner() {
  const { t } = useTranslation()
  const user = useAuthStore((s) => s.user)

  if (!user || !user.email || user.email_verified) return null

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
