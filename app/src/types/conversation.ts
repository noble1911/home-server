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
  /** 'claude_code' when message was produced via Claude Code mode; undefined for normal Butler */
  source?: string
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

export interface VisualContentMessage {
  type: 'visual_content'
  content: string
  title?: string
}

export type LiveKitDataMessage = TranscriptMessage | AgentStateMessage | VisualContentMessage

/** SSE events from POST /api/chat/stream */
/** A drafted email / calendar change waiting for the user's tap-to-approve. */
export interface PendingApproval {
  id: string
  kind: string            // e.g. 'gmail.send', 'calendar.update'
  title: string           // e.g. 'Send email'
  fields: [string, string][]
  body?: string | null
  status: string
  createdAt: string
  expiresAt: string
}

export interface ApprovalResult {
  id: string
  status: 'done' | 'failed' | 'rejected' | string
  result: string
}

export type ChatStreamEvent =
  | { type: 'text_delta'; delta: string }
  | { type: 'tool_start'; tool: string }
  | { type: 'tool_end'; tool: string }
  | { type: 'approval_required'; approval: PendingApproval }
  | { type: 'done'; message_id: string }
