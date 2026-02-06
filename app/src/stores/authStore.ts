import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthTokens, UserRole } from '../types/user'

/**
 * Auth store - handles authentication tokens and role
 * Tokens are device-specific (each device has its own session)
 * User profile data is managed by userStore (synced from API)
 */

interface AuthState {
  tokens: AuthTokens | null
  isAuthenticated: boolean
  hasCompletedOnboarding: boolean
  role: UserRole | null

  // Actions
  setTokens: (tokens: AuthTokens) => void
  setRole: (role: UserRole) => void
  setOnboardingComplete: (complete: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      tokens: null,
      isAuthenticated: false,
      hasCompletedOnboarding: false,
      role: null,

      setTokens: (tokens) => set({
        tokens,
        isAuthenticated: true,
      }),

      setRole: (role) => set({ role }),

      setOnboardingComplete: (hasCompletedOnboarding) => set({
        hasCompletedOnboarding,
      }),

      logout: () => set({
        tokens: null,
        isAuthenticated: false,
        hasCompletedOnboarding: false,
        role: null,
      }),
    }),
    {
      name: 'butler-auth',
      partialize: (state) => ({
        tokens: state.tokens,
        isAuthenticated: state.isAuthenticated,
        hasCompletedOnboarding: state.hasCompletedOnboarding,
        role: state.role,
      }),
    }
  )
)
