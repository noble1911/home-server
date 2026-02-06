import { useCallback } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import type { VoiceStatus } from '../../types/conversation'

interface VoiceButtonProps {
  status: VoiceStatus
  isRecording: boolean
  onStartListening: () => void
  onStopListening: () => void
  connectionError?: string | null
}

export default function VoiceButton({
  status,
  isRecording,
  onStartListening,
  onStopListening,
  connectionError,
}: VoiceButtonProps) {
  const { voiceMode } = useSettingsStore()

  const handlePress = useCallback(() => {
    if (voiceMode === 'push-to-talk') {
      onStartListening()
    } else {
      if (isRecording) {
        onStopListening()
      } else {
        onStartListening()
      }
    }
  }, [voiceMode, isRecording, onStartListening, onStopListening])

  const handleRelease = useCallback(() => {
    if (voiceMode === 'push-to-talk') {
      onStopListening()
    }
  }, [voiceMode, onStopListening])

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
      {connectionError && (
        <span className="text-xs text-red-400">Demo mode</span>
      )}
    </div>
  )
}

function MicIcon({ className, isActive }: { className?: string; isActive?: boolean }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      {isActive ? (
        <>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </>
      ) : (
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
      )}
    </svg>
  )
}
