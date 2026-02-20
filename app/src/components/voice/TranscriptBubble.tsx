import type { Message } from '../../types/conversation'
import MarkdownContent from '../chat/MarkdownContent'

interface TranscriptBubbleProps {
  message: Message
  butlerName: string
}

export default function TranscriptBubble({ message, butlerName }: TranscriptBubbleProps) {
  const isUser = message.role === 'user'

  // User messages: compact right-aligned bubbles
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl px-4 py-2 bg-accent text-white rounded-br-md">
          {message.imageDataUrl && (
            <img
              src={message.imageDataUrl}
              alt="Attached image"
              className="max-w-full max-h-48 rounded-lg mb-2"
            />
          )}
          <p className="text-sm">{message.content}</p>
          <div className="text-xs mt-1 text-blue-200">
            {formatTime(message.timestamp)}
            {message.type === 'voice' && ' • 🎤'}
          </div>
        </div>
      </div>
    )
  }

  // Assistant messages: full-width Gemini-style
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-accent to-blue-700 flex items-center justify-center shrink-0">
          <span className="text-white text-xs font-bold">
            {butlerName.charAt(0).toUpperCase()}
          </span>
        </div>
        <span className="text-sm text-butler-300 font-medium">{butlerName}</span>
        {message.source === 'claude_code' && (
          <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-amber-500/15 text-amber-400 border border-amber-500/30">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            Claude Code
          </span>
        )}
      </div>
      <div className="pl-8 text-butler-100">
        {!message.content && !message.toolStatus ? (
          <div className="flex items-center gap-2 py-1">
            <div className="w-4 h-4 border-2 border-butler-600 border-t-accent rounded-full animate-spin" />
            <span className="text-sm text-butler-400">Thinking…</span>
          </div>
        ) : (
          <MarkdownContent content={message.content} />
        )}
        {message.toolStatus && (
          <p className="text-xs text-butler-400 italic mt-1 animate-pulse">
            {message.toolStatus}
          </p>
        )}
        <div className="text-xs mt-2 text-butler-500">
          {formatTime(message.timestamp)}
          {message.type === 'voice' && ' • 🎤'}
        </div>
      </div>
    </div>
  )
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
