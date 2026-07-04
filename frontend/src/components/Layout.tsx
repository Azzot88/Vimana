import { Outlet } from 'react-router-dom'
import BottomNav from './BottomNav'
import Navbar from './Navbar'

export default function Layout() {
  return (
    <div className="min-h-screen bg-ivory overflow-x-hidden">
      <Navbar />
      <main className="max-w-6xl mx-auto px-4 py-6 pb-[calc(6rem+env(safe-area-inset-bottom))] md:py-8 md:pb-8">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
