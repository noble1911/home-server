import type { Service, ServiceCategory } from '../types/services'
import type { ServiceStatus } from '../services/api'

/**
 * Maps backend health-check service names to frontend service IDs.
 * Only user-facing services are included — infrastructure services
 * (radarr, sonarr, prowlarr, etc.) are shown on the Dashboard instead.
 */
const SERVICE_NAME_MAP: Record<string, string> = {
  'jellyfin': 'jellyfin',
  'audiobookshelf': 'audiobookshelf',
  'calibre-web': 'calibre',
  'immich-server': 'immich',
  'nextcloud': 'nextcloud',
  'homeassistant': 'home-assistant',
}

// Optional: set VITE_SERVICE_HOSTNAME for Tailscale/remote access
// e.g. VITE_SERVICE_HOSTNAME=macmini.tail12345.ts.net
const HOSTNAME = import.meta.env.VITE_SERVICE_HOSTNAME || ''

function serviceUrl(envVar: string, port: number, localDefault: string): string {
  const explicit = import.meta.env[envVar]
  if (explicit) return explicit
  if (HOSTNAME) return `http://${HOSTNAME}:${port}`
  return localDefault
}

export const services: Service[] = [
  {
    id: 'jellyfin',
    name: 'Jellyfin',
    description: 'Movies & TV Shows',
    icon: '🎬',
    url: serviceUrl('VITE_JELLYFIN_URL', 8096, 'http://jellyfin.local'),
    mobileUrl: 'jellyfin://',
    category: 'media',
  },
  {
    id: 'audiobookshelf',
    name: 'Audiobookshelf',
    description: 'Audiobooks & Podcasts',
    icon: '🎧',
    url: serviceUrl('VITE_AUDIOBOOKSHELF_URL', 13378, 'http://audiobooks.local'),
    mobileUrl: 'audiobookshelf://',
    category: 'media',
  },
  {
    id: 'calibre',
    name: 'Calibre-Web',
    description: 'E-Books Library',
    icon: '📚',
    url: serviceUrl('VITE_CALIBRE_URL', 8083, 'http://books.local'),
    category: 'books',
  },
  {
    id: 'immich',
    name: 'Immich',
    description: 'Photo Backup',
    icon: '📷',
    url: serviceUrl('VITE_IMMICH_URL', 2283, 'http://photos.local'),
    mobileUrl: 'immich://',
    category: 'photos',
  },
  {
    id: 'nextcloud',
    name: 'Nextcloud',
    description: 'Files & Documents',
    icon: '📁',
    url: serviceUrl('VITE_NEXTCLOUD_URL', 80, 'http://files.local'),
    mobileUrl: 'nextcloud://',
    category: 'files',
  },
  {
    id: 'home-assistant',
    name: 'Home Assistant',
    description: 'Smart Home Control',
    icon: '🏠',
    url: serviceUrl('VITE_HOMEASSISTANT_URL', 8123, 'http://ha.local'),
    mobileUrl: 'homeassistant://',
    category: 'smart-home',
  },
]

export const categoryLabels: Record<ServiceCategory, string> = {
  'media': 'Media',
  'books': 'Books',
  'photos': 'Photos',
  'files': 'Files',
  'smart-home': 'Smart Home',
}

/**
 * Merge backend health status onto the frontend service list.
 * Services not found in the health response get status 'unknown'.
 */
export function applyHealthStatus(
  frontendServices: Service[],
  healthServices: ServiceStatus[],
): Service[] {
  const statusByFrontendId = new Map<string, 'online' | 'offline'>()
  for (const svc of healthServices) {
    const frontendId = SERVICE_NAME_MAP[svc.name]
    if (frontendId) {
      statusByFrontendId.set(frontendId, svc.status)
    }
  }

  return frontendServices.map(s => ({
    ...s,
    status: statusByFrontendId.get(s.id) ?? 'unknown',
  }))
}
