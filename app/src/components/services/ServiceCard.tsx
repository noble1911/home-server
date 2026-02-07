import type { Service } from '../../types/services'
import { isMobile } from '../../utils/device'

interface ServiceCardProps {
  service: Service
  onSelect: (service: Service) => void
}

export default function ServiceCard({ service, onSelect }: ServiceCardProps) {
  const handleQuickLaunch = (e: React.MouseEvent) => {
    e.stopPropagation()
    const url = isMobile() && service.mobileUrl ? service.mobileUrl : service.url
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  return (
    <button
      onClick={() => onSelect(service)}
      className={`card p-4 text-left hover:bg-butler-700/50 transition-colors group relative${
        service.status === 'offline' ? ' opacity-60 border-red-500/20' : ''
      }`}
    >
      {/* Quick-launch icon */}
      <div
        role="button"
        tabIndex={0}
        onClick={handleQuickLaunch}
        onKeyDown={(e) => { if (e.key === 'Enter') handleQuickLaunch(e as unknown as React.MouseEvent) }}
        className="absolute top-2 right-2 p-1.5 rounded-md text-butler-500 hover:text-accent hover:bg-butler-700 opacity-0 group-hover:opacity-100 transition-opacity"
        title={`Open ${service.name}`}
      >
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      </div>

      <div className="text-3xl mb-2">{service.icon}</div>
      <h3 className="font-medium text-butler-100 group-hover:text-accent transition-colors">
        {service.name}
      </h3>
      <p className="text-xs text-butler-400 mt-1">{service.description}</p>

      {service.status && (
        <div className="flex items-center gap-1 mt-2">
          <div
            className={`w-1.5 h-1.5 rounded-full ${
              service.status === 'online' ? 'bg-green-500' :
              service.status === 'offline' ? 'bg-red-500' : 'bg-butler-500'
            }`}
          />
          <span className="text-xs text-butler-500 capitalize">{service.status}</span>
        </div>
      )}
    </button>
  )
}
