import type { Service, ServiceCategory } from '../types/services'
import type { ServiceStatus } from '../services/api'

/**
 * Maps backend health-check service names to frontend service IDs.
 * Infrastructure without a page of its own (flaresolverr, databases) is
 * shown on the Dashboard instead.
 */
const SERVICE_NAME_MAP: Record<string, string> = {
  'jellyfin': 'jellyfin',
  'audiobookshelf': 'audiobookshelf',
  'lazylibrarian': 'lazylibrarian',
  'immich-server': 'immich',
  'nextcloud': 'nextcloud',
  'homeassistant': 'home-assistant',
  'seerr': 'seerr',
  'radarr': 'radarr',
  'sonarr': 'sonarr',
  'prowlarr': 'prowlarr',
  'bazarr': 'bazarr',
  'qbittorrent': 'qbittorrent',
  'dispatcharr': 'dispatcharr',
}

/**
 * The public domain the app is being used through: "noblehaus.uk" when it's
 * loaded from butler.noblehaus.uk. Worked out at runtime, so a build made
 * without VITE_TUNNEL_DOMAIN can't point every service at
 * butler.noblehaus.uk:<port>. Null on the home network (an IP, localhost or
 * a .local name), where services are reached by port instead.
 */
function publicDomain(): string | null {
  if (import.meta.env.VITE_TUNNEL_DOMAIN) return import.meta.env.VITE_TUNNEL_DOMAIN
  if (typeof window === 'undefined') return null
  const host = window.location.hostname
  const labels = host.split('.')
  if (host === 'localhost' || host.endsWith('.local') || /^[\d.]+$/.test(host) || labels.length < 3) return null
  return labels.slice(1).join('.')
}

// Each service resolves to https://{subdomain}.{domain}; individual
// VITE_<SERVICE>_URL overrides still take priority.
function serviceUrl(envVar: string, port: number, tunnelSubdomain: string): string {
  const explicit = import.meta.env[envVar]
  if (explicit) return explicit
  const domain = publicDomain()
  if (domain) return `https://${tunnelSubdomain}.${domain}`
  // On the home network: same host, the service's own port
  const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  return `http://${host}:${port}`
}

// Pre-compute service URLs so guide text can reference them
const jellyfinUrl = serviceUrl('VITE_JELLYFIN_URL', 8096, 'jellyfin')
const audiobookshelfUrl = serviceUrl('VITE_AUDIOBOOKSHELF_URL', 13378, 'books')
const lazyLibrarianUrl = serviceUrl('VITE_LAZYLIBRARIAN_URL', 5299, 'lazylibrarian')
const immichUrl = serviceUrl('VITE_IMMICH_URL', 2283, 'photos')
const nextcloudUrl = serviceUrl('VITE_NEXTCLOUD_URL', 8080, 'files')
const homeAssistantUrl = serviceUrl('VITE_HOMEASSISTANT_URL', 8123, 'ha')
const seerrUrl = serviceUrl('VITE_SEERR_URL', 5055, 'requests')

export const services: Service[] = [
  {
    id: 'jellyfin',
    access: 'media',
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
    access: 'media',
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
    access: 'media',
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
    id: 'lazylibrarian',
    access: 'media',
    name: 'LazyLibrarian',
    description: 'Book Search & Downloads',
    icon: '📚',
    url: lazyLibrarianUrl,
    category: 'books',
    guide: {
      whatItDoes: 'Search for books and audiobooks, manage downloads, and automatically import them into Audiobookshelf.',
      steps: [
        `Open LazyLibrarian in your browser: ${lazyLibrarianUrl}`,
        'Search for a book by title or author',
        'Select a result and LazyLibrarian will download it via qBittorrent',
        'Once downloaded, LazyLibrarian organizes the file and moves it to the library folder',
        'Audiobookshelf picks up the new files automatically',
      ],
      tips: [
        'You can also ask Butler to find and download books for you via chat or voice',
        'LazyLibrarian supports GoodReads, Google Books, and Open Library for metadata',
        'Prowlarr syncs indexers to LazyLibrarian automatically — no manual indexer setup needed',
      ],
    },
  },
  {
    id: 'immich',
    access: 'media',
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
    access: 'everyone',
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
    access: 'home',
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

/** Admin tools with no public hostname: linked on the home network only. */
const adminTools: Service[] = [
  adminTool('radarr', 'Radarr', 'Movie downloads', '🎥', 7878,
    'Finds and downloads movies, including the ones requested in Seerr or through Butler.'),
  adminTool('sonarr', 'Sonarr', 'TV downloads', '📺', 8989,
    'Finds and downloads TV episodes, including the ones requested in Seerr or through Butler.'),
  adminTool('prowlarr', 'Prowlarr', 'Indexers', '🔎', 9696,
    'Manages the torrent indexers that Radarr, Sonarr and Butler\'s book search use.'),
  adminTool('bazarr', 'Bazarr', 'Subtitles', '💬', 6767,
    'Downloads subtitles for movies and TV. It has no sign-in.'),
  adminTool('qbittorrent', 'qBittorrent', 'Torrent client', '⬇️', 8081,
    'Does the downloading. Sign in with its shared account (below); Butler, Radarr and Sonarr use it too, so it isn\'t changed with your password.'),
  adminTool('dispatcharr', 'Dispatcharr', 'Live TV & guide', '📡', 9191,
    'Feeds IPTV channels and the TV guide to Jellyfin Live TV. Set the provider in Settings → Admin.'),
]

function adminTool(id: string, name: string, description: string, icon: string, port: number, whatItDoes: string): Service {
  return {
    id, name, description, icon, port,
    url: '',
    category: 'admin',
    access: 'admin',
    guide: {
      whatItDoes,
      steps: [
        'Only reachable from the home network',
        id === 'bazarr' || id === 'qbittorrent'
          ? 'Open it from this page while you\'re at home'
          : 'Sign in with your Butler username and password',
      ],
    },
  }
}

/**
 * The services this user can use, with links resolved. Admins see every one,
 * including the home-network admin tools (at http://<lanHost>:<port>); others
 * see what their permissions give them.
 */
export function servicesFor(isAdmin: boolean, permissions: string[], lanHost?: string | null): Service[] {
  const allowed = (s: Service) =>
    isAdmin || s.access === 'everyone' || (s.access !== 'admin' && permissions.includes(s.access))
  // On the home network the page's own host is the server; through the tunnel it isn't
  const host = lanHost || (publicDomain() ? '' : window.location.hostname)
  const tools = host ? adminTools.map(t => ({ ...t, url: `http://${host}:${t.port}` })) : []
  return [...services, ...tools].filter(allowed)
}

export const categoryLabels: Record<ServiceCategory, string> = {
  'media': 'Media',
  'books': 'Books',
  'photos': 'Photos',
  'files': 'Files',
  'smart-home': 'Smart Home',
  'admin': 'Admin tools · home network',
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
