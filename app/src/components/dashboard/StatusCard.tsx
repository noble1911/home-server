interface StatusCardProps {
  name: string
  status: 'online' | 'offline' | 'unknown'
  detail?: string
}

/**
 * Compact service pill. When the service is down, the reason is shown inline
 * (not just in a hover tooltip) so it's readable on a phone.
 */
export default function StatusCard({ name, status, detail }: StatusCardProps) {
  const statusColors = {
    online: 'bg-green-500/20 text-green-400 border-green-500/30',
    offline: 'bg-red-500/20 text-red-400 border-red-500/30',
    unknown: 'bg-butler-600/20 text-butler-400 border-butler-500/30',
  }

  const statusIcons = {
    online: '✓',
    offline: '✕',
    unknown: '?',
  }

  const showDetail = status !== 'online' && !!detail

  return (
    <div
      title={detail ? `${name}: ${detail}` : name}
      className={`
        inline-flex flex-col px-3 py-1.5 rounded-2xl border
        ${statusColors[status]}
      `}
    >
      <div className="inline-flex items-center gap-2">
        <span className="text-xs">{statusIcons[status]}</span>
        <span className="text-sm font-medium">{name}</span>
      </div>
      {showDetail && (
        <span className="text-xs opacity-80 mt-0.5 max-w-[16rem] truncate">{detail}</span>
      )}
    </div>
  )
}
