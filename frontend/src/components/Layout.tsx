import { Outlet } from 'react-router-dom'
import ArchiveNotice from './ArchiveNotice'
import BottomNav from './BottomNav'
import EmailVerifyBanner from './EmailVerifyBanner'
import Navbar from './Navbar'
import PlatformNoticeBanner from './PlatformNoticeBanner'

export default function Layout() {
  return (
    <div className="min-h-screen bg-ivory overflow-x-hidden">
      <Navbar />
      <main className="max-w-6xl mx-auto px-4 py-6 pb-[calc(6rem+env(safe-area-inset-bottom))] md:py-8 md:pb-8 space-y-4">
        <PlatformNoticeBanner surface="all" />
        {/* T3.19 — first, and above everything else the shell says: it changes
            what the rest of the screen means. Renders nothing, and asks the
            server nothing, for an account whose key is alive. */}
        <ArchiveNotice />
        <EmailVerifyBanner />
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
