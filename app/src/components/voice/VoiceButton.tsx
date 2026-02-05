import { useCallback } from 'react'
import { useConversationStore } from '../../stores/conversationStore'
import { useSettingsStore } from '../../stores/settingsStore'
import type { VoiceStatus } from '../../types/conversation'

interface VoiceButtonProps {
  status: VoiceStatus
  isRecording: boolean
}

export default function VoiceButton({ status, isRecording }: VoiceButtonProps) {
  const { setRecording, setVoiceStatus } = useConversationStore()
  const { voiceMode } = useSettingsStore()

  const handlePress = useCallback(() => {
    if (voiceMode === 'push-to-talk') {
      setRecording(true)
      setVoiceStatus('listening')
    } else {
      // Tap to toggle
      setRecording(!isRecording)
      setVoiceStatus(isRecording ? 'idle' : 'listening')
    }
  }, [voiceMode, isRecording, setRecording, setVoiceStatus])

  const handleRelease = useCallback(() => {
    if (voiceMode === 'push-to-talk') {
      setRecording(false)
      setVoiceStatus('processing')
      // Simulate processing then idle
      setTimeout(() => setVoiceStatus('idle'), 1500)
    }
  }, [voiceMode, setRecording, setVoiceStatus])

  const statusColors = {
    idle: 'bg-accent hover:bg-accent-hover',
    listening: 'bg-red-500 hover:bg-red-600 animate-pulse',
    processing: 'bg-yellow-500 hover:bg-yellow-600',
    speaking: 'bg-green-500 hover:bg-green-600',
  }

  const statusLabels = {
    idle: voiceMode === 'push-to-talk' ? 'Hold to speak' : 'Tap to speak',
    listening: 'Listening...',
    processing: 'Processing...',
    speaking: 'Speaking...',
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <button
        onMouseDown={handlePress}
        onMouseUp={handleRelease}
        onMouseLeave={voiceMode === 'push-to-talk' ? handleRelease : undefined}
        onTouchStart={handlePress}
        onTouchEnd={handleRelease}
        className={`
          w-20 h-20 rounded-full flex items-center justify-center
          transition-all duration-200 transform active:scale-95
          ${statusColors[status]}
        `}
        aria-label={statusLabels[status]}
      >
        <MicIcon className="w-10 h-10 text-white" isActive={isRecording} />
      </button>
      <span className="text-sm text-butler-400">{statusLabels[status]}</span>
    </div>
  )
}

function MicIcon({ className, isActive }: { className?: string; isActive?: boolean }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      {isActive ? (
        // Mic with waves
        <>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </>
      ) : (
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
      )}
    </svg>
  )
}
