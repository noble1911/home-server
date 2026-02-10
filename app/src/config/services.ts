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
  'shelfarr': 'shelfarr',
  'immich-server': 'immich',
  'nextcloud': 'nextcloud',
  'homeassistant': 'home-assistant',
  'seerr': 'seerr',
}

// Set VITE_TUNNEL_DOMAIN (e.g. "noblehaus.uk") for Cloudflare Tunnel access.
// Each service resolves to https://{subdomain}.{domain}.
// Individual VITE_<SERVICE>_URL overrides still take priority.
const TUNNEL_DOMAIN = import.meta.env.VITE_TUNNEL_DOMAIN || ''

function serviceUrl(envVar: string, port: number, tunnelSubdomain: string): string {
  const explicit = import.meta.env[envVar]
  if (explicit) return explicit
  if (TUNNEL_DOMAIN) return `https://${tunnelSubdomain}.${TUNNEL_DOMAIN}`
  // Fall back to current hostname — works on LAN without any config
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  return `http://${host}:${port}`
}

// Pre-compute service URLs so guide text can reference them
const jellyfinUrl = serviceUrl('VITE_JELLYFIN_URL', 8096, 'jellyfin')
const audiobookshelfUrl = serviceUrl('VITE_AUDIOBOOKSHELF_URL', 13378, 'books')
const shelfarrUrl = serviceUrl('VITE_SHELFARR_URL', 5056, 'shelfarr')
const immichUrl = serviceUrl('VITE_IMMICH_URL', 2283, 'photos')
const nextcloudUrl = serviceUrl('VITE_NEXTCLOUD_URL', 8080, 'files')
const homeAssistantUrl = serviceUrl('VITE_HOMEASSISTANT_URL', 8123, 'ha')
const seerrUrl = serviceUrl('VITE_SEERR_URL', 5055, 'requests')

export const services: Service[] = [
  {
    id: 'jellyfin',
    name: 'Jellyfin',
    description: 'Movies & TV Shows',
    icon: '🎬',
    url: jellyfinUrl,
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
        name: 'Swiftfin',
        ios: 'https://apps.apple.com/app/swiftfin/id1604098728',
        android: 'https://play.google.com/store/apps/details?id=org.jellyfin.mobile',
      },
      tips: [
        'Use the mobile app for the best experience — it supports offline downloads and background audio',
        'To request new movies or shows, just ask Butler in the chat',
      ],
    },
  },
  {
    id: 'seerr',
    name: 'Seerr',
    description: 'Media Requests',
    icon: '🎬',
    url: seerrUrl,
    category: 'media',
    guide: {
      whatItDoes: 'Request movies and TV shows for the household. Approved requests are sent to Radarr and Sonarr automatically.',
      steps: [
        'Open Seerr in your browser or on your phone',
        'Search for a movie or TV show you want to watch',
        'Click "Request" and choose the quality/seasons you want',
        'Your request will be approved automatically or queued for admin review',
        'Once approved, the media downloads and appears in Jellyfin',
      ],
      tips: [
        'You can also ask Butler to request media — just say "request the new Batman movie"',
        'Check the request list to see the status of your pending requests',
        'Already-available titles are marked so you can watch them right away in Jellyfin',
      ],
    },
  },
  {
    id: 'audiobookshelf',
    name: 'Audiobookshelf',
    description: 'Ebooks & Audiobooks',
    icon: '🎧',
    url: audiobookshelfUrl,
    mobileUrl: 'audiobookshelf://',
    category: 'media',
    guide: {
      whatItDoes: 'Read ebooks and listen to audiobooks with progress sync, sleep timer, and offline downloads across all your devices.',
      steps: [
        'Install the Audiobookshelf app on your phone',
        `Enter the server address when prompted: ${audiobookshelfUrl}`,
        'Log in with your credentials',
        'Browse the library — ebooks and audiobooks are in separate sections',
      ],
      mobileApp: {
        name: 'ShelfPlayer',
        ios: 'https://apps.apple.com/app/shelfplayer/id6475221163',
        android: 'https://play.google.com/store/apps/details?id=com.audiobookshelf.app',
      },
      tips: [
        'Read ebooks in the browser using the built-in EPUB reader',
        'Download audiobooks for offline listening on long trips',
        'Playback speed and sleep timer are in the player controls',
      ],
    },
  },
  {
    id: 'shelfarr',
    name: 'Shelfarr',
    description: 'Book Search & Downloads',
    icon: '📚',
    url: shelfarrUrl,
    category: 'books',
    guide: {
      whatItDoes: 'Search for books, manage downloads, and automatically import them into Audiobookshelf.',
      steps: [
        `Open Shelfarr in your browser: ${shelfarrUrl}`,
        'Search for a book by title or author',
        'Select a result and Shelfarr will download it via qBittorrent',
        'Once downloaded, Shelfarr organizes the file and imports it into Audiobookshelf automatically',
      ],
      tips: [
        'You can also ask Butler to find and download books for you via chat or voice',
        'Ebooks appear in Audiobookshelf after import — read them in the browser or mobile app',
        'Shelfarr connects to Prowlarr for indexers, so make sure your indexers are configured',
      ],
    },
  },
  {
    id: 'immich',
    name: 'Immich',
    description: 'Photo Backup',
    icon: '📷',
    url: immichUrl,
    mobileUrl: 'immich://',
    category: 'photos',
    guide: {
      whatItDoes: 'Automatically back up photos and videos from your phone, and browse them in a beautiful timeline.',
      steps: [
        'Install the Immich app on your phone',
        `Enter the server URL when prompted: ${immichUrl}`,
        'Log in with your credentials',
        'Enable auto-backup in the app settings to protect your photos',
      ],
      mobileApp: {
        name: 'Immich',
        ios: 'https://apps.apple.com/app/immich/id1613945652',
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
    url: nextcloudUrl,
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
    url: homeAssistantUrl,
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
