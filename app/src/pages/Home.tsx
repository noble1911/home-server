import { useEffect, useRef, useCallback, useState } from 'react'
import { useUserStore } from '../stores/userStore'
import { useConversationStore } from '../stores/conversationStore'
import { useLiveKitVoice } from '../hooks/useLiveKitVoice'
import { useInstallPrompt } from '../hooks/useInstallPrompt'
import { getChatHistory, clearChatHistory } from '../services/api'
import ConfirmDialog from '../components/ConfirmDialog'
import type { Message } from '../types/conversation'
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
    historyLoaded,
    setMessages,
    clearMessages,
    prependMessages,
    setLoadingHistory,
    setHasMoreHistory,
    setHistoryLoaded,
  } = useConversationStore()
  const {
    startListening,
    stopListening,
    disconnect,
    audioLevels,
    connectionError,
  } = useLiveKitVoice()
  const { canInstall, isIOS, promptInstall, dismiss } = useInstallPrompt()

  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [isClearing, setIsClearing] = useState(false)

  const butlerName = profile?.butlerName || 'Butler'
  const showWaveform = isRecording || voiceStatus === 'speaking'
  const scrollRef = useRef<HTMLDivElement>(null)

  // Load conversation history on mount (only once per session)
  useEffect(() => {
    if (historyLoaded) return

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
        setHistoryLoaded(true)
      }
    }

    loadHistory()
  }, [historyLoaded, setMessages, setLoadingHistory, setHasMoreHistory, setHistoryLoaded])

  // Auto-scroll to bottom when messages change (including streaming updates)
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages])

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

  const handleClearHistory = useCallback(async () => {
    setIsClearing(true)
    try {
      await clearChatHistory()
      clearMessages()
    } catch {
      // Non-critical — user can retry
    } finally {
      setIsClearing(false)
      setShowClearConfirm(false)
    }
  }, [clearMessages])

  // Disconnect LiveKit when leaving the Home page
  useEffect(() => {
    return () => {
      disconnect()
    }
  }, [disconnect])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Connection error banner */}
      {connectionError && (
        <div className="shrink-0 mx-4 mt-2 px-3 py-2 bg-red-900/30 text-red-300 text-xs rounded-lg">
          Voice server unavailable — using demo mode
        </div>
      )}

      {/* Install prompt banner */}
      {canInstall && (
        <div className="shrink-0 mx-4 mt-2 px-3 py-2 bg-accent/10 border border-accent/30 rounded-lg">
          {isIOS ? (
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs text-butler-200">
                <span className="font-medium text-accent-light">Install Butler</span>
                {' — Tap '}
                <svg className="inline w-4 h-4 -mt-0.5 text-accent-light" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3" />
                </svg>
                {' then "Add to Home Screen"'}
              </p>
              <button onClick={dismiss} className="text-butler-400 hover:text-butler-200 shrink-0 p-0.5" aria-label="Dismiss">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-butler-200">
                <span className="font-medium text-accent-light">Install Butler</span>
                {' — Add to your home screen for quick access'}
              </p>
              <div className="flex items-center gap-1.5 shrink-0">
                <button onClick={promptInstall} className="px-2.5 py-1 bg-accent hover:bg-accent-hover text-white text-xs font-medium rounded transition-colors">
                  Install
                </button>
                <button onClick={dismiss} className="text-butler-400 hover:text-butler-200 p-0.5" aria-label="Dismiss">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Clear history button */}
      {messages.length > 0 && (
        <div className="shrink-0 flex items-center justify-end px-4 pt-2">
          <button
            onClick={() => setShowClearConfirm(true)}
            disabled={isClearing}
            className="flex items-center gap-1 text-xs text-butler-500 hover:text-red-400 disabled:opacity-50"
            aria-label="Clear conversation history"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Clear
          </button>
        </div>
      )}

      {/* Conversation Transcript — scrolls independently */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0 p-4 space-y-4">
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
              Tap the microphone to speak, or type a message below.
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

      {/* Input area — pinned at bottom */}
      <div className="shrink-0 border-t border-butler-800/50 px-4 pt-2 pb-3">
        {/* Waveform — visible only during voice activity */}
        {showWaveform && (
          <div className="flex justify-center pb-2">
            <Waveform isActive={showWaveform} levels={audioLevels} />
          </div>
        )}

        <ChatInput
          voiceStatus={voiceStatus}
          isRecording={isRecording}
          onStartListening={startListening}
          onStopListening={stopListening}
        />
      </div>

      <ConfirmDialog
        open={showClearConfirm}
        title="Clear Conversation History"
        description="This will permanently delete all your conversation history across all devices. This action cannot be undone."
        confirmLabel={isClearing ? 'Clearing...' : 'Clear History'}
        onConfirm={handleClearHistory}
        onCancel={() => setShowClearConfirm(false)}
      />
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
