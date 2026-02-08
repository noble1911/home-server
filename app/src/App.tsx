import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { useUserStore } from './stores/userStore'
import Layout from './components/layout/Layout'
import Home from './pages/Home'
import Services from './pages/Services'
import Downloads from './pages/Downloads'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Onboarding from './pages/Onboarding'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, hasCompletedOnboarding } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  if (!hasCompletedOnboarding) {
    return <Navigate to="/onboarding" replace />
  }

  return <>{children}</>
}

function AppContent() {
  const { isAuthenticated, hasCompletedOnboarding } = useAuthStore()
  const { fetchProfile, profile } = useUserStore()

  // Fetch user profile when authenticated
  useEffect(() => {
    if (isAuthenticated && hasCompletedOnboarding && !profile) {
      fetchProfile()
    }
  }, [isAuthenticated, hasCompletedOnboarding, profile, fetchProfile])

  return (
    <Routes>
      <Route path="/login" element={
        isAuthenticated ? <Navigate to="/" replace /> : <Login />
      } />

      <Route path="/onboarding" element={
        !isAuthenticated ? <Navigate to="/login" replace /> :
        hasCompletedOnboarding ? <Navigate to="/" replace /> :
        <Onboarding />
      } />

      <Route element={
        <ProtectedRoute>
          <Layout />
        </ProtectedRoute>
      }>
        <Route path="/" element={<Home />} />
        <Route path="/services" element={<Services />} />
        <Route path="/downloads" element={<Downloads />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function App() {
  return <AppContent />
}

export default App
