import { useUserStore } from '../../stores/userStore'
import { useConversationStore } from '../../stores/conversationStore'
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import StatusIndicator from './StatusIndicator'

export default function Header() {
  const { profile } = useUserStore()
  const { connectionStatus } = useConversationStore()
  const isOnline = useOnlineStatus()

  // Use profile butler name, fallback to 'Butler' while loading
  const butlerName = profile?.butlerName || 'Butler'

  return (
    <header className="sticky top-0 z-10 bg-butler-900/95 backdrop-blur border-b border-butler-800 safe-top">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-accent to-blue-700 flex items-center justify-center">
            <span className="text-white font-bold text-lg">
              {butlerName.charAt(0).toUpperCase()}
            </span>
          </div>
          <div>
            <h1 className="font-semibold text-butler-100">{butlerName}</h1>
            <p className="text-xs text-butler-400">Your AI Assistant</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {isOnline ? (
            <span className="flex items-center gap-1.5 text-xs text-green-400">
              <span className="w-2 h-2 rounded-full bg-green-500" />
              <span className="hidden sm:inline">Online</span>
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs text-yellow-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 5.636a9 9 0 11-12.728 0M12 9v4m0 4h.01" />
              </svg>
              Offline
            </span>
          )}
          <StatusIndicator status={connectionStatus} />
        </div>
      </div>
    </header>
  )
}
