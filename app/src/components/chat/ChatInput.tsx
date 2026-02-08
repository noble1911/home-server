import { useState, useCallback, useRef } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { useChatStream } from '../../hooks/useChatStream'
import type { ImagePayload } from '../../hooks/useChatStream'
import type { VoiceStatus } from '../../types/conversation'

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
const MAX_SIZE_BYTES = 5 * 1024 * 1024 // 5 MB

interface PendingImage extends ImagePayload {
  dataUrl: string // data URI for preview
}

interface ChatInputProps {
  voiceStatus?: VoiceStatus
  isRecording?: boolean
  onStartListening?: () => void
  onStopListening?: () => void
}

export default function ChatInput({
  voiceStatus = 'idle',
  isRecording = false,
  onStartListening,
  onStopListening,
}: ChatInputProps) {
  const { voiceMode } = useSettingsStore()
  const [message, setMessage] = useState('')
  const [pendingImage, setPendingImage] = useState<PendingImage | null>(null)
  const [imageError, setImageError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { sendMessage, isStreaming, error } = useChatStream()

  // Voice button handlers
  const handleVoicePress = useCallback(() => {
    if (!onStartListening) return
    if (voiceMode === 'push-to-talk') {
      onStartListening()
    } else {
      if (isRecording) {
        onStopListening?.()
      } else {
        onStartListening()
      }
    }
  }, [voiceMode, isRecording, onStartListening, onStopListening])

  const handleVoiceRelease = useCallback(() => {
    if (voiceMode === 'push-to-talk') {
      onStopListening?.()
    }
  }, [voiceMode, onStopListening])

  const micStatusColors: Record<VoiceStatus, string> = {
    idle: 'bg-butler-700 hover:bg-butler-600',
    listening: 'bg-red-500 hover:bg-red-600 animate-pulse',
    processing: 'bg-yellow-500 hover:bg-yellow-600',
    speaking: 'bg-green-500 hover:bg-green-600',
  }

  const processFile = useCallback((file: File) => {
    setImageError(null)
    if (!ALLOWED_TYPES.includes(file.type)) {
      setImageError('Unsupported format. Use JPEG, PNG, GIF, or WebP.')
      return
    }
    if (file.size > MAX_SIZE_BYTES) {
      setImageError('Image too large (max 5 MB).')
      return
    }

    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      const parts = dataUrl.split(',')
      if (parts.length !== 2) {
        setImageError('Invalid image data format.')
        return
      }
      const base64 = parts[1]
      const mediaType = dataUrl.match(/data:(.*?);/)?.[1] || file.type
      setPendingImage({ data: base64, mediaType, dataUrl })
    }
    reader.onerror = () => setImageError('Failed to read image file.')
    reader.readAsDataURL(file)
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) processFile(file)
    // Reset so re-selecting the same file triggers onChange
    e.target.value = ''
  }, [processFile])

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData.items
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (file) processFile(file)
        return
      }
    }
  }, [processFile])

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if ((!message.trim() && !pendingImage) || isStreaming) return

    const text = message.trim() || 'What is this?'
    sendMessage(
      text,
      pendingImage ? { data: pendingImage.data, mediaType: pendingImage.mediaType } : undefined,
    )
    setMessage('')
    setPendingImage(null)
    setImageError(null)
  }, [message, pendingImage, isStreaming, sendMessage])

  return (
    <div>
      {/* Image preview */}
      {pendingImage && (
        <div className="flex items-center gap-2 px-1 pb-2">
          <img
            src={pendingImage.dataUrl}
            alt="Attached"
            className="w-16 h-16 object-cover rounded-lg border border-butler-600"
          />
          <button
            type="button"
            onClick={() => { setPendingImage(null); setImageError(null) }}
            className="text-butler-400 hover:text-red-400 transition-colors"
            aria-label="Remove image"
          >
            <CloseIcon className="w-4 h-4" />
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          onChange={handleFileSelect}
          className="hidden"
        />

        {/* Voice button */}
        {onStartListening && (
          <button
            type="button"
            onMouseDown={handleVoicePress}
            onMouseUp={handleVoiceRelease}
            onMouseLeave={voiceMode === 'push-to-talk' ? handleVoiceRelease : undefined}
            onTouchStart={handleVoicePress}
            onTouchEnd={handleVoiceRelease}
            className={`
              shrink-0 w-10 h-10 rounded-full flex items-center justify-center
              transition-all duration-200 active:scale-95
              ${micStatusColors[voiceStatus]}
            `}
            aria-label={isRecording ? 'Stop listening' : 'Start voice'}
          >
            <MicIcon className="w-5 h-5 text-white" />
          </button>
        )}

        {/* Image attach button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          className="btn px-3 disabled:opacity-50"
          aria-label="Attach image"
        >
          <ImageIcon className="w-5 h-5" />
        </button>

        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onPaste={handlePaste}
          placeholder={
            pendingImage
              ? 'Ask about the image...'
              : isStreaming
                ? 'Waiting for response...'
                : 'Type a message...'
          }
          disabled={isStreaming}
          className="input flex-1 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={(!message.trim() && !pendingImage) || isStreaming}
          className="btn btn-primary px-4 disabled:opacity-50"
          aria-label="Send message"
        >
          <SendIcon className="w-5 h-5" />
        </button>
      </form>
      {(error || imageError) && (
        <p className="text-xs text-red-400 mt-1 px-1">{imageError || error}</p>
      )}
    </div>
  )
}

function SendIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  )
}

function ImageIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  )
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  )
}

function MicIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
    </svg>
  )
}
