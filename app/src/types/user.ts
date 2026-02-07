export type UserRole = 'admin' | 'user'

export type ToolPermission =
  | 'media'
  | 'home'
  | 'location'
  | 'calendar'
  | 'email'
  | 'automation'
  | 'communication'

export interface User {
  id: string
  name: string
  email?: string
  butlerName: string
  role: UserRole
  permissions: ToolPermission[]
  createdAt: string
}

export interface SoulConfig {
  personality: 'casual' | 'formal' | 'balanced'
  verbosity: 'concise' | 'moderate' | 'detailed'
  humor: 'none' | 'subtle' | 'playful'
  customInstructions?: string
}

export interface UserProfile extends User {
  soul: SoulConfig
  facts: UserFact[]
}

export interface UserFact {
  id: string
  content: string
  category: 'preference' | 'personal' | 'routine' | 'other'
  createdAt: string
}

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  expiresAt: number
}

export interface InviteCode {
  code: string
  createdBy: string | null
  usedBy: string | null
  expiresAt: string
  createdAt: string
  usedAt: string | null
  isExpired: boolean
  isUsed: boolean
}

export interface OAuthConnection {
  provider: string
  connected: boolean
  accountId?: string
  connectedAt?: string
}

export interface ServiceCredential {
  service: string
  username: string
  password?: string | null
  status: 'active' | 'failed' | 'decrypt_error'
  errorMessage?: string
  createdAt: string
}

export const SERVICE_DISPLAY_NAMES: Record<string, { label: string; description: string }> = {
  jellyfin: { label: 'Jellyfin', description: 'Movies, TV, Music' },
  audiobookshelf: { label: 'Audiobookshelf', description: 'Audiobooks & Podcasts' },
  nextcloud: { label: 'Nextcloud', description: 'File Sync & Storage' },
  immich: { label: 'Immich', description: 'Photo Management' },
  calibreweb: { label: 'Calibre-Web', description: 'E-Book Library' },
}

export interface AdminUser {
  id: string
  name: string
  role: UserRole
  permissions: ToolPermission[]
}

export const PERMISSION_INFO: Record<ToolPermission, { label: string; description: string }> = {
  media: { label: 'Media', description: 'Radarr, Sonarr, Readarr, Immich, Jellyfin' },
  home: { label: 'Smart Home', description: 'Home Assistant, entity control' },
  location: { label: 'Location', description: 'Phone location tracking' },
  calendar: { label: 'Calendar', description: 'Google Calendar' },
  email: { label: 'Email', description: 'Gmail' },
  automation: { label: 'Automation', description: 'Scheduled tasks' },
  communication: { label: 'Communication', description: 'WhatsApp messages' },
}
