import { Outlet } from 'react-router-dom'
import Header from './Header'
import BottomNav from './BottomNav'

export default function Layout() {
  return (
    <div className="flex flex-col min-h-screen">
      <Header />
      <main className="flex-1 overflow-y-auto pb-20 md:pb-0">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
