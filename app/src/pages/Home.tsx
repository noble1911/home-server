import { useEffect, useRef } from 'react'
import { useUserStore } from '../stores/userStore'
import { useConversationStore } from '../stores/conversationStore'
import { useLiveKitVoice } from '../hooks/useLiveKitVoice'
import { useInstallPrompt } from '../hooks/useInstallPrompt'
import VoiceButton from '../components/voice/VoiceButton'
import Waveform from '../components/voice/Waveform'
import TranscriptBubble from '../components/voice/TranscriptBubble'
import ChatInput from '../components/chat/ChatInput'

export default function Home() {
  const { profile } = useUserStore()
  const { messages, voiceStatus, isRecording } = useConversationStore()
  const {
    startListening,
    stopListening,
    disconnect,
    audioLevels,
    connectionError,
  } = useLiveKitVoice()
  const { canInstall, isIOS, promptInstall, dismiss } = useInstallPrompt()

  const butlerName = profile?.butlerName || 'Butler'
  const showWaveform = isRecording || voiceStatus === 'speaking'
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when messages change (including streaming updates)
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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

      {/* Install prompt banner */}
      {canInstall && (
        <div className="mx-4 mt-2 px-3 py-2 bg-accent/10 border border-accent/30 rounded-lg">
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

      {/* Conversation Transcript */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
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
        ) : (
          messages.map((message) => (
            <TranscriptBubble
              key={message.id}
              message={message}
              butlerName={butlerName}
            />
          ))
        )}
        <div ref={messagesEndRef} />
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
