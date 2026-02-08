import type { Message } from '../../types/conversation'

interface TranscriptBubbleProps {
  message: Message
  butlerName: string
}

export default function TranscriptBubble({ message, butlerName }: TranscriptBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`
          max-w-[80%] rounded-2xl px-4 py-2
          ${isUser
            ? 'bg-accent text-white rounded-br-md'
            : 'bg-butler-800 text-butler-100 rounded-bl-md'
          }
        `}
      >
        {!isUser && (
          <div className="text-xs text-butler-400 mb-1">{butlerName}</div>
        )}
        {message.imageDataUrl && (
          <img
            src={message.imageDataUrl}
            alt="Attached image"
            className="max-w-full max-h-48 rounded-lg mb-2"
          />
        )}
        {message.role === 'assistant' && !message.content && !message.toolStatus ? (
          <p className="text-sm text-butler-400 animate-pulse">...</p>
        ) : (
          <p className="text-sm">{message.content}</p>
        )}
        {message.toolStatus && (
          <p className="text-xs text-butler-400 italic mt-1 animate-pulse">
            {message.toolStatus}
          </p>
        )}
        <div className={`text-xs mt-1 ${isUser ? 'text-blue-200' : 'text-butler-500'}`}>
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
