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

/** Data messages sent between LiveKit Agent and PWA */
export interface TranscriptMessage {
  type: 'user_transcript' | 'assistant_transcript'
  text: string
  isFinal: boolean
}

export interface AgentStateMessage {
  type: 'agent_state'
  state: 'thinking' | 'speaking' | 'idle'
}

export type LiveKitDataMessage = TranscriptMessage | AgentStateMessage
