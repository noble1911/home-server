/**
 * Generic SSE-over-POST utility.
 *
 * Uses fetch + ReadableStream (not EventSource) because we need:
 *  - POST requests (to send the message body)
 *  - Custom Authorization headers (for JWT auth)
 */

import { ApiError, getAuthToken } from './api'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export interface SSECallbacks<T> {
  onEvent: (event: T) => void
  onError?: (error: Error) => void
  onDone?: () => void
}

/**
 * POST to an SSE endpoint and invoke callbacks for each parsed event.
 *
 * SSE format expected:
 *   data: {"type":"text_delta","delta":"hi"}\n\n
 *   data: [DONE]\n\n
 */
export async function streamSSE<T>(
  endpoint: string,
  body: unknown,
  callbacks: SSECallbacks<T>,
  signal?: AbortSignal,
): Promise<void> {
  const token = await getAuthToken()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    })
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      callbacks.onDone?.()
      return
    }
    callbacks.onError?.(err instanceof Error ? err : new Error(String(err)))
    return
  }

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({
      message: `HTTP ${response.status}: Request failed`,
    }))
    callbacks.onError?.(new ApiError(response.status, errBody.message || `HTTP ${response.status}`))
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    callbacks.onError?.(new Error('Response body is not readable'))
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Split on double-newline (SSE event boundary)
      const parts = buffer.split('\n\n')
      // Keep the last (potentially incomplete) part in the buffer
      buffer = parts.pop() || ''

      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data: ')) continue

        const payload = line.slice(6) // strip "data: "
        if (payload === '[DONE]') {
          callbacks.onDone?.()
          return
        }

        try {
          callbacks.onEvent(JSON.parse(payload) as T)
        } catch {
          // Skip malformed JSON lines
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      callbacks.onDone?.()
      return
    }
    callbacks.onError?.(err instanceof Error ? err : new Error(String(err)))
  } finally {
    reader.releaseLock()
  }

  // If we exit the loop without [DONE], still signal completion
  callbacks.onDone?.()
}
