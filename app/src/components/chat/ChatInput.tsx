import { useState, useCallback } from 'react'
import { useConversationStore } from '../../stores/conversationStore'
import type { Message } from '../../types/conversation'

export default function ChatInput() {
  const [message, setMessage] = useState('')
  const { addMessage, setVoiceStatus } = useConversationStore()

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()

    if (!message.trim()) return

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: message.trim(),
      type: 'text',
      timestamp: new Date().toISOString(),
    }

    addMessage(userMessage)
    setMessage('')
    setVoiceStatus('processing')

    // Simulate butler response - in production this calls the API
    setTimeout(() => {
      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `I received your message: "${userMessage.content}". This is a demo response. In production, I'll connect to the Butler API.`,
        type: 'text',
        timestamp: new Date().toISOString(),
      }
      addMessage(assistantMessage)
      setVoiceStatus('idle')
    }, 1500)
  }, [message, addMessage, setVoiceStatus])

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Type a message..."
        className="input flex-1"
      />
      <button
        type="submit"
        disabled={!message.trim()}
        className="btn btn-primary px-4 disabled:opacity-50"
        aria-label="Send message"
      >
        <SendIcon className="w-5 h-5" />
      </button>
    </form>
  )
}

function SendIcon({ className }: { className?: string }) {
  return (
    <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  )
}
