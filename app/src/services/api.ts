/**
 * Base API client for Butler backend
 * All user data is stored server-side and synced across devices
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function getAuthToken(): Promise<string | null> {
  const authData = localStorage.getItem('butler-auth')
  if (!authData) return null

  try {
    const { state } = JSON.parse(authData)
    return state?.tokens?.accessToken || null
  } catch {
    return null
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getAuthToken()

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  })

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
