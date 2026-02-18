import type { ConnectionStatus } from '../../types/conversation'

interface StatusIndicatorProps {
  status: ConnectionStatus
}

const statusConfig: Record<ConnectionStatus, { color: string; label: string }> = {
  connected: { color: 'bg-green-500', label: 'Connected' },
  connecting: { color: 'bg-yellow-500', label: 'Connecting' },
  disconnected: { color: 'bg-butler-500', label: 'Offline' },
  error: { color: 'bg-red-500', label: 'Error' },
}

export default function StatusIndicator({ status }: StatusIndicatorProps) {
  // Don't show indicator in default disconnected state — it's not useful
  // and "Offline" is misleading (text chat still works without voice)
  if (status === 'disconnected') return null

  const config = statusConfig[status]

  return (
    <div className="flex items-center gap-2">
      <div className={`w-2 h-2 rounded-full ${config.color} ${status === 'connecting' ? 'animate-pulse' : ''}`} />
      <span className="text-xs text-butler-400 hidden sm:inline">{config.label}</span>
    </div>
  )
}
