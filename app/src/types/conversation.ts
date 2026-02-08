export type MessageRole = 'user' | 'assistant'
export type MessageType = 'voice' | 'text'

export interface Message {
  id: string
  role: MessageRole
  content: string
  type: MessageType
  timestamp: string
  toolStatus?: string
  /** data:image/...;base64,... — set for current-session image messages only */
  imageDataUrl?: string
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

/** SSE events from POST /api/chat/stream */
export type ChatStreamEvent =
  | { type: 'text_delta'; delta: string }
  | { type: 'tool_start'; tool: string }
  | { type: 'tool_end'; tool: string }
  | { type: 'done'; message_id: string }
