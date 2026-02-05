import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthTokens } from '../types/user'

/**
 * Auth store - ONLY handles authentication tokens
 * Tokens are device-specific (each device has its own session)
 * User profile data is managed by userStore (synced from API)
 */

interface AuthState {
  tokens: AuthTokens | null
  isAuthenticated: boolean
  hasCompletedOnboarding: boolean

  // Actions
  setTokens: (tokens: AuthTokens) => void
  setOnboardingComplete: (complete: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      tokens: null,
      isAuthenticated: false,
      hasCompletedOnboarding: false,

      setTokens: (tokens) => set({
        tokens,
        isAuthenticated: true,
      }),

      setOnboardingComplete: (hasCompletedOnboarding) => set({
        hasCompletedOnboarding,
      }),

      logout: () => set({
        tokens: null,
        isAuthenticated: false,
        hasCompletedOnboarding: false,
      }),
    }),
    {
      name: 'butler-auth',
      // Only persist tokens - they're device-specific
      partialize: (state) => ({
        tokens: state.tokens,
        isAuthenticated: state.isAuthenticated,
        hasCompletedOnboarding: state.hasCompletedOnboarding,
      }),
    }
  )
)
