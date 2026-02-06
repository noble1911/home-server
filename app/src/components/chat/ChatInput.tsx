import { useState, useCallback } from 'react'
import { useChatStream } from '../../hooks/useChatStream'

export default function ChatInput() {
  const [message, setMessage] = useState('')
  const { sendMessage, isStreaming, error } = useChatStream()

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim() || isStreaming) return

    sendMessage(message.trim())
    setMessage('')
  }, [message, isStreaming, sendMessage])

  return (
    <div>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={isStreaming ? 'Waiting for response...' : 'Type a message...'}
          disabled={isStreaming}
          className="input flex-1 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!message.trim() || isStreaming}
          className="btn btn-primary px-4 disabled:opacity-50"
          aria-label="Send message"
        >
          <SendIcon className="w-5 h-5" />
        </button>
      </form>
      {error && (
        <p className="text-xs text-red-400 mt-1 px-1">{error}</p>
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
