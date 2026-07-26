import { Outlet } from 'react-router-dom'
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
        <EmailVerifyBanner />
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
