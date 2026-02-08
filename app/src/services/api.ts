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

async function tryRefresh(): Promise<boolean> {
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

export interface SystemStorageResponse {
  volumes: StorageVolume[]
}

export interface SystemStatsResponse {
  platform: string
  architecture: string
  uptimeSeconds: number | null
  uptimeFormatted: string | null
  memory: {
    total: number
    used: number
    available: number
    percent: number
    totalFormatted: string
    usedFormatted: string
  } | null
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
