import { useCallback, useEffect, useState } from 'react'
import { api } from '../services/api'

interface VapidKeyResponse {
  vapidPublicKey: string
}

/**
 * Convert a base64url-encoded VAPID key to a Uint8Array for PushManager.subscribe().
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const arr = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) {
    arr[i] = raw.charCodeAt(i)
  }
  return arr
}

interface UsePushNotificationsReturn {
  isSupported: boolean
  permission: NotificationPermission
  isSubscribed: boolean
  isLoading: boolean
  subscribe: () => Promise<void>
  unsubscribe: () => Promise<void>
  sendTest: () => Promise<void>
}

export function usePushNotifications(): UsePushNotificationsReturn {
  const isSupported = 'Notification' in window && 'PushManager' in window && 'serviceWorker' in navigator
  const [permission, setPermission] = useState<NotificationPermission>(
    isSupported ? Notification.permission : 'denied'
  )
  const [isSubscribed, setIsSubscribed] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // Check existing subscription on mount
  useEffect(() => {
    if (!isSupported) {
      setIsLoading(false)
      return
    }

    navigator.serviceWorker.ready.then(async (reg) => {
      const sub = await reg.pushManager.getSubscription()
      setIsSubscribed(!!sub)
      setPermission(Notification.permission)
      setIsLoading(false)
    }).catch(() => {
      setIsLoading(false)
    })
  }, [isSupported])

  const subscribe = useCallback(async () => {
    if (!isSupported) return
    setIsLoading(true)

    try {
      // Request notification permission
      const perm = await Notification.requestPermission()
      setPermission(perm)
      if (perm !== 'granted') {
        setIsLoading(false)
        return
      }

      // Get VAPID public key from backend
      const { vapidPublicKey } = await api.get<VapidKeyResponse>('/push/vapid-key')
      if (!vapidPublicKey) {
        console.warn('Push notifications not configured: no VAPID key')
        setIsLoading(false)
        return
      }

      // Subscribe via PushManager
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey).buffer as ArrayBuffer,
      })

      // Send subscription to backend
      const key = sub.getKey('p256dh')
      const auth = sub.getKey('auth')
      if (!key || !auth) throw new Error('Missing subscription keys')

      await api.post('/push/subscribe', {
        endpoint: sub.endpoint,
        keys: {
          p256dh: btoa(String.fromCharCode(...new Uint8Array(key))),
          auth: btoa(String.fromCharCode(...new Uint8Array(auth))),
        },
      })

      setIsSubscribed(true)
    } catch (err) {
      console.error('Push subscription failed:', err)
    } finally {
      setIsLoading(false)
    }
  }, [isSupported])

  const unsubscribe = useCallback(async () => {
    if (!isSupported) return
    setIsLoading(true)

    try {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()

      if (sub) {
        // Remove from backend first (endpoint as query param)
        await api.delete(`/push/subscribe?endpoint=${encodeURIComponent(sub.endpoint)}`)

        // Unsubscribe from browser
        await sub.unsubscribe()
      }

      setIsSubscribed(false)
    } catch (err) {
      console.error('Push unsubscription failed:', err)
    } finally {
      setIsLoading(false)
    }
  }, [isSupported])

  const sendTest = useCallback(async () => {
    await api.post('/push/test')
  }, [])

  return {
    isSupported,
    permission,
    isSubscribed,
    isLoading,
    subscribe,
    unsubscribe,
    sendTest,
  }
}
