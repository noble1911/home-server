import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Settings store - LOCAL device preferences only
 * These are intentionally device-specific (not synced)
 * Examples: voice input mode depends on device capabilities
 */

type VoiceMode = 'push-to-talk' | 'tap-to-toggle'

interface SettingsState {
  // Device-specific settings (not synced)
  voiceMode: VoiceMode
  audioInputDevice: string | null
  audioOutputDevice: string | null
  // Read Butler's voice replies aloud; off = answers appear as text only
  speakReplies: boolean

  // Actions
  setVoiceMode: (mode: VoiceMode) => void
  setSpeakReplies: (enabled: boolean) => void
  setAudioInputDevice: (deviceId: string | null) => void
  setAudioOutputDevice: (deviceId: string | null) => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      voiceMode: 'push-to-talk',
      audioInputDevice: null,
      audioOutputDevice: null,
      speakReplies: true,

      setVoiceMode: (voiceMode) => set({ voiceMode }),
      setSpeakReplies: (speakReplies) => set({ speakReplies }),
      setAudioInputDevice: (audioInputDevice) => set({ audioInputDevice }),
      setAudioOutputDevice: (audioOutputDevice) => set({ audioOutputDevice }),
    }),
    {
      name: 'butler-device-settings',
    }
  )
)
