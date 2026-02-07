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

// Optional: set VITE_SERVICE_HOSTNAME for Cloudflare Tunnel/remote access
// e.g. VITE_SERVICE_HOSTNAME=home.yourdomain.com
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
    guide: {
      whatItDoes: 'Stream movies, TV shows, anime, and music from your home server to any device.',
      steps: [
        'Open Jellyfin in your browser or install the mobile app',
        'Log in with the username and password from your account setup',
        'Browse libraries — Movies, TV Shows, Music, and Anime are each in their own section',
        'Start watching! Progress syncs across all your devices',
      ],
      mobileApp: {
        name: 'Jellyfin',
        ios: 'https://apps.apple.com/app/jellyfin-mobile/id1480732313',
        android: 'https://play.google.com/store/apps/details?id=org.jellyfin.mobile',
      },
      tips: [
        'Use the mobile app for the best experience — it supports offline downloads and background audio',
        'To request new movies or shows, just ask Butler in the chat',
      ],
    },
  },
  {
    id: 'audiobookshelf',
    name: 'Audiobookshelf',
    description: 'Audiobooks & Podcasts',
    icon: '🎧',
    url: serviceUrl('VITE_AUDIOBOOKSHELF_URL', 13378, 'http://audiobooks.local'),
    mobileUrl: 'audiobookshelf://',
    category: 'media',
    guide: {
      whatItDoes: 'Listen to audiobooks and podcasts with progress tracking, sleep timer, and offline downloads.',
      steps: [
        'Install the Audiobookshelf app on your phone',
        'Enter the server address when prompted',
        'Log in with your credentials',
        'Browse the library and tap any book to start listening',
      ],
      mobileApp: {
        name: 'Audiobookshelf',
        ios: 'https://apps.apple.com/app/audiobookshelf/id1642275455',
        android: 'https://play.google.com/store/apps/details?id=com.audiobookshelf.app',
      },
      tips: [
        'Download audiobooks for offline listening on long trips',
        'Playback speed and sleep timer are in the player controls',
      ],
    },
  },
  {
    id: 'calibre',
    name: 'Calibre-Web',
    description: 'E-Books Library',
    icon: '📚',
    url: serviceUrl('VITE_CALIBRE_URL', 8083, 'http://books.local'),
    category: 'books',
    guide: {
      whatItDoes: 'Browse, read, and download ebooks from your home library. Connect reader apps via OPDS for the best mobile experience.',
      steps: [
        'Open Calibre-Web in your browser and log in with your credentials',
        'Find a book and tap its cover — use "Read in Browser" or download it',
        'For mobile apps, add the OPDS feed in your reader: use your server URL followed by /opds',
        'Enter your Calibre-Web username and password when the reader app asks',
      ],
      tips: [
        'OPDS lets reader apps like KOReader, Moon+ Reader, and FBReader browse and download books directly — no browser needed',
        'EPUB format works best on most devices — use the Convert button if you need a different format',
        'Apple Books (iOS) and Moon+ Reader (Android) give the best reading experience for downloaded books',
      ],
    },
  },
  {
    id: 'immich',
    name: 'Immich',
    description: 'Photo Backup',
    icon: '📷',
    url: serviceUrl('VITE_IMMICH_URL', 2283, 'http://photos.local'),
    mobileUrl: 'immich://',
    category: 'photos',
    guide: {
      whatItDoes: 'Automatically back up photos and videos from your phone, and browse them in a beautiful timeline.',
      steps: [
        'Install the Immich app on your phone',
        'Enter the server URL when prompted',
        'Log in with your credentials',
        'Enable auto-backup in the app settings to protect your photos',
      ],
      mobileApp: {
        name: 'Immich',
        ios: 'https://apps.apple.com/app/immich/id1613945686',
        android: 'https://play.google.com/store/apps/details?id=app.alextran.immich',
      },
      tips: [
        'Enable background backup so new photos upload automatically',
        'Use the web interface to browse your full photo timeline on a big screen',
      ],
    },
  },
  {
    id: 'nextcloud',
    name: 'Nextcloud',
    description: 'Files & Documents',
    icon: '📁',
    url: serviceUrl('VITE_NEXTCLOUD_URL', 80, 'http://files.local'),
    mobileUrl: 'nextcloud://',
    category: 'files',
    guide: {
      whatItDoes: 'Sync and share files across all your devices — like your own private Dropbox.',
      steps: [
        'Open Nextcloud in your browser or install the app',
        'Log in with your credentials',
        'Upload files via the web or sync folders using the desktop/mobile app',
        'Share files or folders with other household members',
      ],
      mobileApp: {
        name: 'Nextcloud',
        ios: 'https://apps.apple.com/app/nextcloud/id1125420102',
        android: 'https://play.google.com/store/apps/details?id=com.nextcloud.client',
      },
      tips: [
        'Install the desktop app to auto-sync folders between your computer and the server',
        'You can share files with anyone in the household without needing external cloud storage',
      ],
    },
  },
  {
    id: 'home-assistant',
    name: 'Home Assistant',
    description: 'Smart Home Control',
    icon: '🏠',
    url: serviceUrl('VITE_HOMEASSISTANT_URL', 8123, 'http://ha.local'),
    mobileUrl: 'homeassistant://',
    category: 'smart-home',
    guide: {
      whatItDoes: 'Control smart lights, switches, sensors, and automations from one place.',
      steps: [
        'Open Home Assistant in your browser or install the app',
        'Log in with your Home Assistant account',
        'The dashboard shows your devices — tap to control them',
        'Ask Butler to control devices by voice for hands-free operation',
      ],
      mobileApp: {
        name: 'Home Assistant',
        ios: 'https://apps.apple.com/app/home-assistant/id1099568401',
        android: 'https://play.google.com/store/apps/details?id=io.homeassistant.companion.android',
      },
      tips: [
        'The mobile app enables location-based automations (e.g. turn on lights when you arrive home)',
        'Ask the admin to set up automations for common routines',
      ],
    },
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
