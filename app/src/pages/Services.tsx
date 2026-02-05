import ServiceCard from '../components/services/ServiceCard'
import type { Service, ServiceCategory } from '../types/services'

// Service definitions - URLs will be configured per-deployment
const services: Service[] = [
  {
    id: 'jellyfin',
    name: 'Jellyfin',
    description: 'Movies & TV Shows',
    icon: '🎬',
    url: 'http://jellyfin.local',
    mobileUrl: 'jellyfin://',
    category: 'media',
  },
  {
    id: 'audiobookshelf',
    name: 'Audiobookshelf',
    description: 'Audiobooks & Podcasts',
    icon: '🎧',
    url: 'http://audiobooks.local',
    mobileUrl: 'audiobookshelf://',
    category: 'media',
  },
  {
    id: 'calibre',
    name: 'Calibre-Web',
    description: 'E-Books Library',
    icon: '📚',
    url: 'http://books.local',
    category: 'books',
  },
  {
    id: 'immich',
    name: 'Immich',
    description: 'Photo Backup',
    icon: '📷',
    url: 'http://photos.local',
    mobileUrl: 'immich://',
    category: 'photos',
  },
  {
    id: 'nextcloud',
    name: 'Nextcloud',
    description: 'Files & Documents',
    icon: '📁',
    url: 'http://files.local',
    mobileUrl: 'nextcloud://',
    category: 'files',
  },
  {
    id: 'home-assistant',
    name: 'Home Assistant',
    description: 'Smart Home Control',
    icon: '🏠',
    url: 'http://ha.local',
    mobileUrl: 'homeassistant://',
    category: 'smart-home',
  },
]

const categoryLabels: Record<ServiceCategory, string> = {
  'media': 'Media',
  'books': 'Books',
  'photos': 'Photos',
  'files': 'Files',
  'smart-home': 'Smart Home',
}

export default function Services() {
  const categories = [...new Set(services.map(s => s.category))] as ServiceCategory[]

  return (
    <div className="p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-butler-100">Services</h1>
        <p className="text-sm text-butler-400">Quick access to your home server apps</p>
      </div>

      {categories.map(category => (
        <div key={category}>
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
            {categoryLabels[category]}
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {services
              .filter(s => s.category === category)
              .map(service => (
                <ServiceCard key={service.id} service={service} />
              ))}
          </div>
        </div>
      ))}
    </div>
  )
}
