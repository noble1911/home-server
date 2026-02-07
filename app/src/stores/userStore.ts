import { create } from 'zustand'
import { api } from '../services/api'
import type { UserProfile, SoulConfig, UserFact, NotificationPrefs } from '../types/user'

/**
 * User store - manages user profile data synced from API
 * This data is stored server-side and shared across all devices
 * Local state is just a cache - always fetch fresh on mount
 */

interface UserState {
  profile: UserProfile | null
  isLoading: boolean
  error: string | null

  // Actions
  fetchProfile: () => Promise<void>
  updateProfile: (updates: Partial<UserProfile>) => Promise<void>
  updateButlerName: (name: string) => Promise<void>
  updateSoul: (soul: Partial<SoulConfig>) => Promise<void>
  updateNotifications: (phone?: string, prefs?: Partial<NotificationPrefs>) => Promise<void>
  addFact: (content: string, category: UserFact['category']) => Promise<void>
  removeFact: (factId: string) => Promise<void>
  clearAllFacts: () => void
  clearProfile: () => void
}

export const useUserStore = create<UserState>((set, get) => ({
  profile: null,
  isLoading: false,
  error: null,

  fetchProfile: async () => {
    set({ isLoading: true, error: null })
    try {
      const profile = await api.get<UserProfile>('/user/profile')
      set({ profile, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch profile',
        isLoading: false
      })
    }
  },

  updateProfile: async (updates) => {
    const current = get().profile
    if (!current) return

    // Optimistic update
    set({ profile: { ...current, ...updates } })

    try {
      const updated = await api.put<UserProfile>('/user/profile', updates)
      set({ profile: updated })
    } catch (error) {
      // Revert on error
      set({
        profile: current,
        error: error instanceof Error ? error.message : 'Failed to update profile'
      })
    }
  },

  updateButlerName: async (butlerName) => {
    const current = get().profile
    if (!current) return

    set({ profile: { ...current, butlerName } })

    try {
      await api.put('/user/butler', { butlerName })
    } catch (error) {
      set({
        profile: current,
        error: error instanceof Error ? error.message : 'Failed to update butler name'
      })
    }
  },

  updateSoul: async (soulUpdates) => {
    const current = get().profile
    if (!current) return

    const newSoul = { ...current.soul, ...soulUpdates }
    set({ profile: { ...current, soul: newSoul } })

    try {
      await api.put('/user/soul', newSoul)
    } catch (error) {
      set({
        profile: current,
        error: error instanceof Error ? error.message : 'Failed to update soul config'
      })
    }
  },

  updateNotifications: async (phone, prefs) => {
    const current = get().profile
    if (!current) return

    const optimistic = { ...current }
    if (phone !== undefined) optimistic.phone = phone
    if (prefs) {
      optimistic.notificationPrefs = { ...current.notificationPrefs, ...prefs }
    }
    set({ profile: optimistic })

    try {
      const body: Record<string, unknown> = {}
      if (phone !== undefined) body.phone = phone
      if (prefs) body.notificationPrefs = { ...current.notificationPrefs, ...prefs }
      const updated = await api.put<UserProfile>('/user/notifications', body)
      set({ profile: updated })
    } catch (error) {
      set({
        profile: current,
        error: error instanceof Error ? error.message : 'Failed to update notifications'
      })
    }
  },

  addFact: async (content, category) => {
    const current = get().profile
    if (!current) return

    try {
      const newFact = await api.post<UserFact>('/user/facts', { content, category })
      set({
        profile: {
          ...current,
          facts: [...current.facts, newFact]
        }
      })
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to add fact' })
    }
  },

  removeFact: async (factId) => {
    const current = get().profile
    if (!current) return

    // Optimistic update
    set({
      profile: {
        ...current,
        facts: current.facts.filter(f => f.id !== factId)
      }
    })

    try {
      await api.delete(`/user/facts/${factId}`)
    } catch (error) {
      set({
        profile: current,
        error: error instanceof Error ? error.message : 'Failed to remove fact'
      })
    }
  },

  clearAllFacts: () => set((state) => ({
    profile: state.profile ? { ...state.profile, facts: [] } : null,
  })),

  clearProfile: () => set({ profile: null, error: null }),
}))
