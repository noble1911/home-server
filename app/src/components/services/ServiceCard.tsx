import type { Service } from '../../types/services'
import { isMobile } from '../../utils/device'

interface ServiceCardProps {
  service: Service
}

export default function ServiceCard({ service }: ServiceCardProps) {
  const handleClick = () => {
    const url = isMobile() && service.mobileUrl ? service.mobileUrl : service.url
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  return (
    <button
      onClick={handleClick}
      className="card p-4 text-left hover:bg-butler-700/50 transition-colors group"
    >
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
