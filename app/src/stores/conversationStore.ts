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
  historyLoaded: boolean

  // Actions
  addMessage: (message: Message) => void
  prependMessages: (messages: Message[]) => void
  updateMessage: (id: string, updates: Partial<Pick<Message, 'content' | 'toolStatus'>>) => void
  setMessages: (messages: Message[]) => void
  clearMessages: () => void
  setConnectionStatus: (status: ConnectionStatus) => void
  setVoiceStatus: (status: VoiceStatus) => void
  setRecording: (isRecording: boolean) => void
  setLoadingHistory: (loading: boolean) => void
  setHasMoreHistory: (hasMore: boolean) => void
  setHistoryLoaded: (loaded: boolean) => void
}

export const useConversationStore = create<ConversationState>((set) => ({
  messages: [],
  connectionStatus: 'disconnected',
  voiceStatus: 'idle',
  isRecording: false,
  isLoadingHistory: false,
  hasMoreHistory: true,
  historyLoaded: false,

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),

  prependMessages: (messages) => set((state) => ({
    messages: [...messages, ...state.messages],
  })),

  updateMessage: (id, updates) => set((state) => ({
    messages: state.messages.map((m) =>
      m.id === id ? { ...m, ...updates } : m
    ),
  })),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [], hasMoreHistory: true, historyLoaded: false }),

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  setVoiceStatus: (status) => set({ voiceStatus: status }),

  setRecording: (isRecording) => set({ isRecording }),

  setLoadingHistory: (loading) => set({ isLoadingHistory: loading }),

  setHasMoreHistory: (hasMore) => set({ hasMoreHistory: hasMore }),

  setHistoryLoaded: (loaded) => set({ historyLoaded: loaded }),
}))
