export type MessageRole = 'user' | 'assistant'
export type MessageType = 'voice' | 'text'

export interface Message {
  id: string
  role: MessageRole
  content: string
  type: MessageType
  timestamp: string
}

export interface Conversation {
  id: string
  messages: Message[]
  startedAt: string
  endedAt?: string
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error'
export type VoiceStatus = 'idle' | 'listening' | 'processing' | 'speaking'
