export type UserRole = 'admin' | 'user'

export type ToolPermission =
  | 'media'
  | 'home'
  | 'location'
  | 'calendar'
  | 'email'
  | 'automation'
  | 'communication'
  | 'claude_code'

export interface User {
  id: string
  name: string
  email?: string
  phone?: string
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
  voice?: string
}

export interface VoiceOption {
  id: string
  name: string
  accent: string
  gender: string
}

export const VOICE_OPTIONS: VoiceOption[] = [
  { id: 'af_bella', name: 'Bella', accent: 'American', gender: 'Female' },
  { id: 'af_sarah', name: 'Sarah', accent: 'American', gender: 'Female' },
  { id: 'am_adam', name: 'Adam', accent: 'American', gender: 'Male' },
  { id: 'am_michael', name: 'Michael', accent: 'American', gender: 'Male' },
  { id: 'bf_emma', name: 'Emma', accent: 'British', gender: 'Female' },
  { id: 'bm_george', name: 'George', accent: 'British', gender: 'Male' },
]

export const DEFAULT_VOICE = 'bf_emma'

export type NotificationCategory =
  | 'download'
  | 'reminder'
  | 'weather'
  | 'smart_home'
  | 'calendar'
  | 'general'

export interface NotificationPrefs {
  enabled: boolean
  categories: NotificationCategory[]
  quietHoursStart?: string
  quietHoursEnd?: string
}

export interface UserProfile extends User {
  soul: SoulConfig
  facts: UserFact[]
  notificationPrefs: NotificationPrefs
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
  permissions: ToolPermission[]
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
  lazylibrarian: { label: 'LazyLibrarian', description: 'Book Search & Downloads' },
  homeassistant: { label: 'Home Assistant', description: 'Smart Home Control' },
}

export interface AdminUser {
  id: string
  name: string
  role: UserRole
  permissions: ToolPermission[]
}

export const PERMISSION_INFO: Record<ToolPermission, { label: string; description: string }> = {
  media: { label: 'Media', description: 'Radarr, Sonarr, Immich, Jellyfin, Books' },
  home: { label: 'Smart Home', description: 'Home Assistant, entity control' },
  location: { label: 'Location', description: 'Phone location tracking' },
  calendar: { label: 'Calendar', description: 'Google Calendar' },
  email: { label: 'Email', description: 'Gmail' },
  automation: { label: 'Automation', description: 'Scheduled tasks' },
  communication: { label: 'Communication', description: 'WhatsApp messages' },
  claude_code: { label: 'Claude Code', description: 'Run agentic tasks using Claude Code on the server' },
}
