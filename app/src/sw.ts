/// <reference lib="webworker" />

import { cleanupOutdatedCaches, precacheAndRoute } from 'workbox-precaching'

declare let self: ServiceWorkerGlobalScope

// Activate new SW immediately instead of waiting for all tabs to close
self.skipWaiting()
self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

// Workbox injects the precache manifest here during build
precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

// ── Push notification handling ───────────────────────────────────────

interface PushPayload {
  title: string
  body: string
  url?: string
  category?: string
}

self.addEventListener('push', (event) => {
  if (!event.data) return

  let payload: PushPayload
  try {
    payload = event.data.json() as PushPayload
  } catch {
    payload = { title: 'Butler', body: event.data.text() }
  }

  const options: NotificationOptions = {
    body: payload.body,
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    tag: payload.category || 'general',
    data: { url: payload.url || '/' },
  }

  event.waitUntil(self.registration.showNotification(payload.title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const url = (event.notification.data?.url as string) || '/'

  // Focus an existing window or open a new one
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(url)
          return client.focus()
        }
      }
      return self.clients.openWindow(url)
    })
  )
})
