import { useRef, useState, useCallback, useEffect } from 'react'
import { useConversationStore } from '../stores/conversationStore'
import { streamSSE } from '../services/sse'
import type { ChatStreamEvent, Message } from '../types/conversation'

const TOOL_LABELS: Record<string, string> = {
  weather: 'Checking weather...',
  home_assistant: 'Controlling smart home...',
  list_ha_entities: 'Looking up devices...',
  phone_location: 'Checking location...',
  remember_fact: 'Remembering that...',
  recall_facts: 'Recalling what I know...',
  get_user: 'Looking up user info...',
  radarr: 'Searching movies...',
  sonarr: 'Searching TV shows...',
  readarr: 'Searching books...',
  jellyfin: 'Checking media library...',
  immich: 'Searching photos...',
  google_calendar: 'Checking calendar...',
  gmail: 'Checking email...',
  server_health: 'Checking server health...',
  storage_monitor: 'Checking storage...',
  whatsapp: 'Sending WhatsApp message...',
}

function getToolLabel(name: string): string {
  return TOOL_LABELS[name] || `Using ${name.replace(/_/g, ' ')}...`
}

export interface UseChatStreamReturn {
  sendMessage: (content: string) => void
  cancelStream: () => void
  isStreaming: boolean
  error: string | null
}

export function useChatStream(): UseChatStreamReturn {
  const { addMessage, updateMessage, setVoiceStatus } = useConversationStore()
  const abortRef = useRef<AbortController | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const cancelStream = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
    setVoiceStatus('idle')
  }, [setVoiceStatus])

  // Abort on unmount
  useEffect(() => () => { abortRef.current?.abort() }, [])

  const sendMessage = useCallback((content: string) => {
    // Abort any in-flight stream
    abortRef.current?.abort()

    setError(null)
    setIsStreaming(true)
    setVoiceStatus('processing')

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      type: 'text',
      timestamp: new Date().toISOString(),
    }
    addMessage(userMessage)

    const assistantId = crypto.randomUUID()
    const assistantMessage: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      type: 'text',
      timestamp: new Date().toISOString(),
    }
    addMessage(assistantMessage)

    const controller = new AbortController()
    abortRef.current = controller

    let accumulated = ''

    streamSSE<ChatStreamEvent>(
      '/chat/stream',
      { message: content },
      {
        onEvent(event) {
          switch (event.type) {
            case 'text_delta':
              accumulated += event.delta
              updateMessage(assistantId, { content: accumulated })
              break
            case 'tool_start':
              updateMessage(assistantId, { toolStatus: getToolLabel(event.tool) })
              break
            case 'tool_end':
              updateMessage(assistantId, { toolStatus: undefined })
              break
            case 'done':
              break
          }
        },
        onError(err) {
          const msg = err.message || 'Something went wrong'
          setError(msg)
          // If we never got content, remove the empty placeholder
          if (!accumulated) {
            updateMessage(assistantId, { content: 'Failed to get a response.' })
          }
          setIsStreaming(false)
          setVoiceStatus('idle')
        },
        onDone() {
          setIsStreaming(false)
          setVoiceStatus('idle')
        },
      },
      controller.signal,
    )
  }, [addMessage, updateMessage, setVoiceStatus])

  return { sendMessage, cancelStream, isStreaming, error }
}
