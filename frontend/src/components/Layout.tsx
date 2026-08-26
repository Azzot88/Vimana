import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import ArchiveNotice from './ArchiveNotice'
import BottomNav from './BottomNav'
import EmailVerifyBanner from './EmailVerifyBanner'
import Navbar from './Navbar'
import PlatformNoticeBanner from './PlatformNoticeBanner'

/** T_UX.23 — `children` in addition to `<Outlet/>`.
 *
 *  `/carrier` and `/send` are one address showing two different screens: the
 *  landing to a guest, the panel to a signed-in account. The landing brings its
 *  own header and footer, so the shell cannot be a parent route — the choice
 *  happens inside the component, and the authenticated branch wraps itself.
 *  Every existing nested route keeps using `<Outlet/>` untouched. */
export default function Layout({ children }: { children?: ReactNode }) {
  const { t } = useTranslation()
  return (
    <div className="min-h-[100dvh] bg-ivory overflow-x-hidden">
      {/* T_UX.7 pt.1 — first stop for the keyboard. Above the nav in the DOM,
          invisible until focused. Without it every keyboard user tabs through
          the whole navigation on every page before reaching the content. */}
      <a href="#main" className="skip-link">
        {t('common.skipToContent')}
      </a>
      <Navbar />
      <main
        id="main"
        className="max-w-6xl mx-auto px-4 py-6 pb-[calc(6rem+env(safe-area-inset-bottom))] md:py-8 md:pb-8 space-y-4"
      >
        <PlatformNoticeBanner surface="all" />
        {/* T3.19 — first, and above everything else the shell says: it changes
            what the rest of the screen means. Renders nothing, and asks the
            server nothing, for an account whose key is alive. */}
        <ArchiveNotice />
        <EmailVerifyBanner />
        {children ?? <Outlet />}
      </main>
      <BottomNav />
    </div>
  )
}
