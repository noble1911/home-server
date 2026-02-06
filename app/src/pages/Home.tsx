import { useEffect, useRef, useCallback } from 'react'
import { useUserStore } from '../stores/userStore'
import { useConversationStore } from '../stores/conversationStore'
import { useLiveKitVoice } from '../hooks/useLiveKitVoice'
import { getChatHistory } from '../services/api'
import type { Message } from '../types/conversation'
import VoiceButton from '../components/voice/VoiceButton'
import Waveform from '../components/voice/Waveform'
import TranscriptBubble from '../components/voice/TranscriptBubble'
import ChatInput from '../components/chat/ChatInput'

export default function Home() {
  const { profile } = useUserStore()
  const {
    messages,
    voiceStatus,
    isRecording,
    isLoadingHistory,
    hasMoreHistory,
    setMessages,
    prependMessages,
    setLoadingHistory,
    setHasMoreHistory,
  } = useConversationStore()
  const {
    startListening,
    stopListening,
    disconnect,
    audioLevels,
    connectionError,
  } = useLiveKitVoice()

  const butlerName = profile?.butlerName || 'Butler'
  const showWaveform = isRecording || voiceStatus === 'speaking'
  const scrollRef = useRef<HTMLDivElement>(null)
  const initialLoadDone = useRef(false)

  // Load conversation history on mount
  useEffect(() => {
    if (initialLoadDone.current) return
    initialLoadDone.current = true

    async function loadHistory() {
      setLoadingHistory(true)
      try {
        const data = await getChatHistory()
        // API returns newest-first; reverse for chronological display
        const chronological: Message[] = data.messages
          .map((m) => ({
            id: m.id,
            role: m.role as Message['role'],
            content: m.content,
            type: m.type as Message['type'],
            timestamp: m.timestamp,
          }))
          .reverse()
        setMessages(chronological)
        setHasMoreHistory(data.hasMore)
      } catch {
        // History loading is non-critical; app still works without it
      } finally {
        setLoadingHistory(false)
      }
    }

    loadHistory()
  }, [setMessages, setLoadingHistory, setHasMoreHistory])

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages.length])

  // Load older messages
  const loadMore = useCallback(async () => {
    if (isLoadingHistory || !hasMoreHistory || messages.length === 0) return

    const oldestTimestamp = messages[0].timestamp
    const el = scrollRef.current
    const prevScrollHeight = el?.scrollHeight ?? 0

    setLoadingHistory(true)
    try {
      const data = await getChatHistory(oldestTimestamp)
      const older: Message[] = data.messages
        .map((m) => ({
          id: m.id,
          role: m.role as Message['role'],
          content: m.content,
          type: m.type as Message['type'],
          timestamp: m.timestamp,
        }))
        .reverse()
      prependMessages(older)
      setHasMoreHistory(data.hasMore)

      // Preserve scroll position after prepend
      requestAnimationFrame(() => {
        if (el) {
          el.scrollTop = el.scrollHeight - prevScrollHeight
        }
      })
    } catch {
      // Non-critical — user can retry
    } finally {
      setLoadingHistory(false)
    }
  }, [isLoadingHistory, hasMoreHistory, messages, prependMessages, setLoadingHistory, setHasMoreHistory])

  // Disconnect LiveKit when leaving the Home page
  useEffect(() => {
    return () => {
      disconnect()
    }
  }, [disconnect])

  return (
    <div className="flex flex-col h-full min-h-[calc(100vh-8rem)]">
      {/* Connection error banner */}
      {connectionError && (
        <div className="mx-4 mt-2 px-3 py-2 bg-red-900/30 text-red-300 text-xs rounded-lg">
          Voice server unavailable — using demo mode
        </div>
      )}

      {/* Conversation Transcript */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Load more button */}
        {hasMoreHistory && messages.length > 0 && (
          <div className="flex justify-center">
            <button
              onClick={loadMore}
              disabled={isLoadingHistory}
              className="text-xs text-butler-400 hover:text-butler-200 disabled:opacity-50 py-2 px-4"
            >
              {isLoadingHistory ? 'Loading…' : 'Load earlier messages'}
            </button>
          </div>
        )}

        {/* Initial loading spinner */}
        {isLoadingHistory && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="w-6 h-6 border-2 border-butler-600 border-t-accent rounded-full animate-spin" />
            <p className="text-butler-400 text-sm mt-3">Loading messages…</p>
          </div>
        )}

        {/* Empty state */}
        {!isLoadingHistory && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-8">
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-accent to-blue-700 flex items-center justify-center mb-4">
              <span className="text-white font-bold text-3xl">
                {butlerName.charAt(0).toUpperCase()}
              </span>
            </div>
            <h2 className="text-xl font-semibold text-butler-100 mb-2">
              Hi, I'm {butlerName}
            </h2>
            <p className="text-butler-400 max-w-sm">
              Press and hold the microphone button to speak, or type a message below.
            </p>
          </div>
        )}

        {/* Messages with date separators */}
        {messages.map((message, index) => {
          const showSeparator =
            index === 0 ||
            !isSameDay(messages[index - 1].timestamp, message.timestamp)

          return (
            <div key={message.id}>
              {showSeparator && (
                <DateSeparator timestamp={message.timestamp} />
              )}
              <TranscriptBubble message={message} butlerName={butlerName} />
            </div>
          )
        })}
      </div>

      {/* Voice Interface */}
      <div className="p-4 space-y-4">
        {showWaveform && (
          <div className="flex justify-center">
            <Waveform isActive={showWaveform} levels={audioLevels} />
          </div>
        )}

        <div className="flex justify-center">
          <VoiceButton
            status={voiceStatus}
            isRecording={isRecording}
            onStartListening={startListening}
            onStopListening={stopListening}
            connectionError={connectionError}
          />
        </div>

        <ChatInput />
      </div>
    </div>
  )
}

// --- Helpers ---

function isSameDay(a: string, b: string): boolean {
  const da = new Date(a)
  const db = new Date(b)
  return (
    da.getFullYear() === db.getFullYear() &&
    da.getMonth() === db.getMonth() &&
    da.getDate() === db.getDate()
  )
}

function formatDateLabel(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const diffDays = Math.round(
    (today.getTime() - target.getTime()) / (1000 * 60 * 60 * 24),
  )

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  })
}

function DateSeparator({ timestamp }: { timestamp: string }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="flex-1 border-t border-butler-700" />
      <span className="text-xs text-butler-500">{formatDateLabel(timestamp)}</span>
      <div className="flex-1 border-t border-butler-700" />
    </div>
  )
}
