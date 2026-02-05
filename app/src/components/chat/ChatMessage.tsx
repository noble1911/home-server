import type { Message } from '../../types/conversation'

interface ChatMessageProps {
  message: Message
  butlerName: string
}

export default function ChatMessage({ message, butlerName }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-butler-700 flex items-center justify-center mr-2 flex-shrink-0">
          <span className="text-xs font-bold text-butler-300">
            {butlerName.charAt(0).toUpperCase()}
          </span>
        </div>
      )}

      <div
        className={`
          max-w-[75%] rounded-2xl px-4 py-2
          ${isUser
            ? 'bg-accent text-white'
            : 'bg-butler-800 text-butler-100 border border-butler-700'
          }
        `}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
      </div>

      {isUser && (
        <div className="w-8 h-8 rounded-full bg-butler-600 flex items-center justify-center ml-2 flex-shrink-0">
          <span className="text-xs font-bold text-butler-200">You</span>
        </div>
      )}
    </div>
  )
}
