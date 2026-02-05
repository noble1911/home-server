import { useUserStore } from '../../stores/userStore'
import { useConversationStore } from '../../stores/conversationStore'
import StatusIndicator from './StatusIndicator'

export default function Header() {
  const { profile } = useUserStore()
  const { connectionStatus } = useConversationStore()

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

        <StatusIndicator status={connectionStatus} />
      </div>
    </header>
  )
}
