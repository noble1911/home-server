interface StatusCardProps {
  name: string
  status: 'online' | 'offline' | 'unknown'
}

export default function StatusCard({ name, status }: StatusCardProps) {
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

  return (
    <div
      className={`
        inline-flex items-center gap-2 px-3 py-1.5 rounded-full border
        ${statusColors[status]}
      `}
    >
      <span className="text-xs">{statusIcons[status]}</span>
      <span className="text-sm font-medium">{name}</span>
    </div>
  )
}
