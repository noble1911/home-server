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

  // Actions
  addMessage: (message: Message) => void
  updateMessage: (id: string, updates: Partial<Pick<Message, 'content' | 'toolStatus'>>) => void
  setMessages: (messages: Message[]) => void
  clearMessages: () => void
  setConnectionStatus: (status: ConnectionStatus) => void
  setVoiceStatus: (status: VoiceStatus) => void
  setRecording: (isRecording: boolean) => void
}

export const useConversationStore = create<ConversationState>((set) => ({
  messages: [],
  connectionStatus: 'disconnected',
  voiceStatus: 'idle',
  isRecording: false,

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),

  updateMessage: (id, updates) => set((state) => ({
    messages: state.messages.map((m) =>
      m.id === id ? { ...m, ...updates } : m
    ),
  })),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [] }),

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  setVoiceStatus: (status) => set({ voiceStatus: status }),

  setRecording: (isRecording) => set({ isRecording }),
}))
