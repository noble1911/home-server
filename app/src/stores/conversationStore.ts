import { create } from 'zustand'
import type { Message, ConnectionStatus, VoiceStatus } from '../types/conversation'

/**
 * Conversation store - session state only
 * Messages are not persisted locally - fetched from API when needed
 * This store handles the current active conversation UI state
 */

interface ConversationState {
  messages: Message[]
  connectionStatus: ConnectionStatus
  voiceStatus: VoiceStatus
  isRecording: boolean
  isLoadingHistory: boolean
  hasMoreHistory: boolean

  // Actions
  addMessage: (message: Message) => void
  prependMessages: (messages: Message[]) => void
  setMessages: (messages: Message[]) => void
  clearMessages: () => void
  setConnectionStatus: (status: ConnectionStatus) => void
  setVoiceStatus: (status: VoiceStatus) => void
  setRecording: (isRecording: boolean) => void
  setLoadingHistory: (loading: boolean) => void
  setHasMoreHistory: (hasMore: boolean) => void
}

export const useConversationStore = create<ConversationState>((set) => ({
  messages: [],
  connectionStatus: 'disconnected',
  voiceStatus: 'idle',
  isRecording: false,
  isLoadingHistory: false,
  hasMoreHistory: true,

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),

  prependMessages: (messages) => set((state) => ({
    messages: [...messages, ...state.messages],
  })),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [], hasMoreHistory: true }),

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  setVoiceStatus: (status) => set({ voiceStatus: status }),

  setRecording: (isRecording) => set({ isRecording }),

  setLoadingHistory: (loading) => set({ isLoadingHistory: loading }),

  setHasMoreHistory: (hasMore) => set({ hasMoreHistory: hasMore }),
}))
