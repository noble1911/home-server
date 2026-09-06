/**
 * Base API client for Butler backend
 * All user data is stored server-side and synced across devices
 *
 * Includes auto-refresh: when an access token expires (401), the client
 * silently exchanges the refresh token for a new pair and retries.
 */

import { useAuthStore } from '../stores/authStore'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export function getAuthToken(): string | null {
  const authData = localStorage.getItem('butler-auth')
  if (!authData) return null

  try {
    const { state } = JSON.parse(authData)
    return state?.tokens?.accessToken || null
  } catch {
    return null
  }
}

function getRefreshToken(): string | null {
  const authData = localStorage.getItem('butler-auth')
  if (!authData) return null

  try {
    const { state } = JSON.parse(authData)
    return state?.tokens?.refreshToken || null
  } catch {
    return null
  }
}

function buildHeaders(token: string | null, extra?: HeadersInit): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(extra as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

// Refresh lock — prevents multiple concurrent refresh attempts
let refreshPromise: Promise<boolean> | null = null

export async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) {
    // Another request is already refreshing — wait for it
    return refreshPromise
  }

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return false

    try {
      // Use raw fetch to avoid infinite loop through request()
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refreshToken }),
      })

      if (!response.ok) {
        useAuthStore.getState().logout()
        return false
      }

      const data = await response.json()
      useAuthStore.getState().setTokens(data.tokens)
      if (data.role) {
        useAuthStore.getState().setRole(data.role)
      }
      return true
    } catch {
      useAuthStore.getState().logout()
      return false
    }
  })()

  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

// Endpoints that should never trigger a refresh attempt
const NO_REFRESH_ENDPOINTS = ['/auth/refresh', '/auth/redeem-invite']

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken()
  const headers = buildHeaders(token, options.headers)

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  })

  // Auto-refresh on 401 (but not for auth endpoints themselves)
  if (response.status === 401 && !NO_REFRESH_ENDPOINTS.includes(endpoint)) {
    const refreshed = await tryRefresh()
    if (refreshed) {
      // Retry with the new token
      const newToken = getAuthToken()
      const retryHeaders = buildHeaders(newToken, options.headers)
      const retryResponse = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers: retryHeaders,
      })

      if (!retryResponse.ok) {
        const error = await retryResponse.json().catch(() => ({ message: 'Request failed' }))
        throw new ApiError(retryResponse.status, error.message || `HTTP ${retryResponse.status}`)
      }
      if (retryResponse.status === 204) return undefined as T
      return retryResponse.json()
    }
    // Refresh failed — logout already happened in tryRefresh
    throw new ApiError(401, 'Session expired')
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }))
    throw new ApiError(response.status, error.message || `HTTP ${response.status}`)
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: 'GET' }),

  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined
    }),

  put: <T>(endpoint: string, data: unknown) =>
    request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data)
    }),

  delete: <T>(endpoint: string) => request<T>(endpoint, { method: 'DELETE' }),
}

export { ApiError }

/** LiveKit token response from POST /api/auth/token */
export interface LiveKitTokenResponse {
  livekit_token: string
  room_name: string
}

/** Fetch a LiveKit room token for voice sessions */
export function getLiveKitToken(): Promise<LiveKitTokenResponse> {
  return api.post<LiveKitTokenResponse>('/auth/token')
}

/** A single message from conversation history */
export interface HistoryMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  type: 'voice' | 'text'
  timestamp: string
  source?: string | null  // 'claude_code' or null/undefined for normal Butler
}

/** Paginated chat history response */
export interface ChatHistoryResponse {
  messages: HistoryMessage[]
  hasMore: boolean
}

/** Fetch paginated conversation history */
export function getChatHistory(
  before?: string,
  limit: number = 50,
): Promise<ChatHistoryResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (before) params.set('before', before)
  return api.get<ChatHistoryResponse>(`/chat/history?${params}`)
}

/** Clear all conversation history for the current user */
export function clearChatHistory(): Promise<void> {
  return api.delete('/chat/history')
}

/** Clear all learned facts for the current user */
export function clearUserFacts(): Promise<void> {
  return api.delete('/user/facts')
}

/** Permanently delete the current user's account and all data */
export function deleteUserAccount(): Promise<void> {
  return api.delete('/user/account')
}

// ── System monitoring ──────────────────────────────────────────────

export interface ServiceStatus {
  name: string
  status: 'online' | 'offline'
  stack: string
  detail?: string
}

export interface SystemHealthResponse {
  services: ServiceStatus[]
  summary: { total: number; healthy: number }
}

export interface StorageVolume {
  name: string
  total: number
  used: number
  free: number
  percent: number
  totalFormatted: string
  usedFormatted: string
  freeFormatted: string
  categories?: Record<string, { bytes: number; formatted: string }>
}

export interface StorageCategory {
  label: string
  bytes: number | null
  formatted: string | null
  linkedTo: string | null
  exists: boolean
}

export interface StorageDrive {
  name: string
  path: string
  role: 'system' | 'downloads' | 'library' | string | null
  mounted: boolean
  total?: number
  used?: number
  free?: number
  percent?: number
  totalFormatted?: string
  usedFormatted?: string
  freeFormatted?: string
  categories?: StorageCategory[]
}

export interface StoragePool {
  name: string
  drives: string[]
  total: number
  used: number
  free: number
  percent: number
  totalFormatted: string
  usedFormatted: string
  freeFormatted: string
}

export interface SystemStorageResponse {
  volumes: StorageVolume[]
  /** Present when the host agent is reachable: every drive, incl. ones not mounted into Docker. */
  drives?: StorageDrive[]
  pool?: StoragePool
  categoriesAt?: number | null
  /** false when macOS privacy settings block the host agent from reading a drive */
  diskAccess?: boolean
  agentPython?: string | null
}

export interface ProcessUsage {
  name: string
  cpu: number | null
  rss: number | null
  rssFormatted: string
}

export interface ContainerUsage {
  name: string
  cpu: number | null
  memory: number | null
  memoryFormatted: string
}

/** Bare-metal numbers from the host agent (null when it is not running). */
export interface HostStats {
  sampledAt: number | null
  uptimeSeconds: number | null
  uptimeFormatted: string | null
  cpu: { percent: number | null; cores: number | null; load: number[] | null; perCore: number[] | null }
  memory: { total: number | null; used: number | null; percent: number | null; totalFormatted: string; usedFormatted: string }
  swap: { total: number | null; used: number | null; percent: number | null; usedFormatted: string; totalFormatted: string }
  apps: ProcessUsage[]
  topCpu: ProcessUsage[]
  topMemory: ProcessUsage[]
  containers: ContainerUsage[]
}

export interface SystemStatsResponse {
  platform: string
  architecture: string
  uptimeSeconds: number | null
  uptimeFormatted: string | null
  cpu: { percent: number } | null
  memory: {
    dockerUsed: number
    dockerTotal: number
    dockerPercent: number
    dockerUsedFormatted: string
    dockerTotalFormatted: string
    hostTotalGb: number | null
  } | null
  host: HostStats | null
}

export function getSystemHealth(): Promise<SystemHealthResponse> {
  return api.get<SystemHealthResponse>('/system/health')
}

export function getSystemStorage(): Promise<SystemStorageResponse> {
  return api.get<SystemStorageResponse>('/system/storage')
}

export function getSystemStats(): Promise<SystemStatsResponse> {
  return api.get<SystemStatsResponse>('/system/stats')
}

export interface AlertInfo {
  id: number
  key: string
  type: string
  severity: 'info' | 'warning' | 'critical' | string
  message: string
  firstTriggeredAt: string | null
  lastTriggeredAt: string | null
}

export interface SystemAlertsResponse {
  alerts: AlertInfo[]
  summary: { total: number }
}

export function getSystemAlerts(): Promise<SystemAlertsResponse> {
  return api.get<SystemAlertsResponse>('/system/alerts')
}

// ── Media inbox (Downloads/Complete → library) ──────────────────────

export interface InboxArrSummary {
  app: 'sonarr' | 'radarr'
  files: number
  matched: number
  titles: string[]
  episodes: number | null
  rejections: string[]
}

export interface InboxItem {
  name: string
  isDir: boolean
  bytes: number
  modifiedAt: number
  ageDays: number
  seeding: boolean
  empty?: boolean
  leftover?: boolean
  suggestion: {
    app: 'sonarr' | 'radarr'
    titles: string[]
    episodes?: number | null
    files: number
    matched: number
    partial: boolean
    inLibrary: number
    allInLibrary: boolean
  } | null
  sonarr: InboxArrSummary | null
  radarr: InboxArrSummary | null
}

export interface InboxDestination {
  key: string
  label: string
  path: string
}

export interface InboxResponse {
  path?: string
  error?: string
  items: InboxItem[]
  summary?: { count: number; bytes: number; importable: number; seeding: number; inLibrary: number; leftovers: number }
  destinations?: InboxDestination[]
}

export interface InboxImportResult {
  name: string
  app?: 'sonarr' | 'radarr'
  mode?: 'move' | 'copy'
  commandId?: number
  files?: number
  status: 'queued' | 'unmatched' | 'failed'
  error?: string
}

export interface ArrCommandStatus {
  name: string
  app: 'sonarr' | 'radarr'
  commandId: number
  mode: 'move' | 'copy'
  status: string
  message?: string | null
}

export interface MoveJob {
  id: string
  source: string
  destination: string
  status: 'queued' | 'running' | 'done' | 'failed'
  totalBytes: number
  copiedBytes: number
  files: number
  filesDone: number
  error: string | null
  startedAt: number
  finishedAt: number | null
}

export function getMediaInbox(): Promise<InboxResponse> {
  return api.get<InboxResponse>('/media/inbox')
}

export function importInboxItems(names: string[]): Promise<{ results: InboxImportResult[] }> {
  return api.post('/media/inbox/import', { names })
}

export function moveInboxItem(name: string, destination: string): Promise<{ job: MoveJob }> {
  return api.post('/media/inbox/move', { name, destination })
}

export function getInboxJobs(): Promise<{ commands: ArrCommandStatus[]; moves: MoveJob[] }> {
  return api.get('/media/inbox/jobs')
}

export function refreshJellyfinLibrary(): Promise<{ ok: boolean }> {
  return api.post('/media/library/refresh')
}

// ── Downloads (qBittorrent proxy) ────────────────────────────────────

export interface TorrentInfo {
  hash: string
  name: string
  progress: number
  size: number
  sizeFormatted: string
  downloaded: number
  downloadedFormatted: string
  dlSpeed: number
  dlSpeedFormatted: string
  upSpeed: number
  upSpeedFormatted: string
  eta: number
  etaFormatted: string
  state: string
  category: string
  addedOn: string | null
}

export interface DownloadsSummary {
  total: number
  downloading: number
  seeding: number
  paused: number
  dlSpeed: number
  dlSpeedFormatted: string
}

export interface DownloadsResponse {
  torrents: TorrentInfo[]
  summary: DownloadsSummary
}

export function getDownloads(): Promise<DownloadsResponse> {
  return api.get<DownloadsResponse>('/downloads')
}

export function pauseTorrent(hash: string): Promise<void> {
  return api.post(`/downloads/${hash}/pause`)
}

export function resumeTorrent(hash: string): Promise<void> {
  return api.post(`/downloads/${hash}/resume`)
}

export function deleteTorrent(hash: string, deleteFiles = false): Promise<void> {
  return api.delete(`/downloads/${hash}?deleteFiles=${deleteFiles}`)
}
