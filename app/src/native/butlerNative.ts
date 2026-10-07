/**
 * Bridge to the Butler Android app (#214).
 *
 * The app is a Capacitor shell that loads this same website, so all of this
 * code also runs in a normal browser, where `isNativeApp` is false and
 * nothing here is used. Native side: app/android/.../ButlerNotificationsPlugin.java.
 */
import { Capacitor, registerPlugin, type PluginListenerHandle } from '@capacitor/core'
import { Browser } from '@capacitor/browser'
import { api } from '../services/api'

export const isNativeApp = Capacitor.isNativePlatform()

export interface PhoneNotificationStatus {
  enabled: boolean
  connected: boolean
  lastError?: string | null
  deviceId?: string | null
  notificationsAllowed: boolean
  batteryOptimized: boolean
  deviceName: string
  versionName: string
  versionCode: number
}

interface ButlerNotificationsPlugin {
  start(options: { baseUrl: string; deviceToken: string; deviceId: string; sinceId: number }): Promise<void>
  stop(): Promise<void>
  status(): Promise<PhoneNotificationStatus>
  requestNotificationPermission(): Promise<{ granted: boolean }>
  openBatterySettings(): Promise<void>
  openNotificationSettings(): Promise<void>
  addListener(event: 'notificationOpened', listener: (e: { url: string }) => void): Promise<PluginListenerHandle>
}

export const ButlerNotifications = registerPlugin<ButlerNotificationsPlugin>('ButlerNotifications')

interface DeviceRegistration {
  deviceId: string
  deviceToken: string
  sinceId: number
}

/** Register this phone with Butler and start the notification connection. */
export async function enablePhoneNotifications(): Promise<PhoneNotificationStatus> {
  await ButlerNotifications.requestNotificationPermission()
  const { deviceName } = await ButlerNotifications.status()
  const reg = await api.post<DeviceRegistration>('/devices', { name: deviceName || 'Android phone' })
  await ButlerNotifications.start({
    baseUrl: window.location.origin,
    deviceToken: reg.deviceToken,
    deviceId: reg.deviceId,
    sinceId: reg.sinceId,
  })
  return ButlerNotifications.status()
}

/** Stop notifications on this phone; with `unregister`, also forget it on the server. */
export async function disablePhoneNotifications({ unregister = true } = {}): Promise<void> {
  const { deviceId } = await ButlerNotifications.status()
  if (unregister && deviceId) {
    try {
      await api.delete(`/devices/${encodeURIComponent(deviceId)}`)
    } catch {
      // Already gone, or signed out: the server ignores devices unseen for a week.
    }
  }
  await ButlerNotifications.stop()
}

/** Open a URL in the system browser (Custom Tab) rather than inside the app. */
export function openExternal(url: string): void {
  void Browser.open({ url })
}

const RELEASES_URL = 'https://api.github.com/repos/noble1911/home-server/releases?per_page=20'

export interface AppUpdate {
  versionCode: number
  name: string
  url: string
}

/** The newest "Build Android app" release, if it's newer than this install. */
export async function checkForAppUpdate(currentVersionCode: number): Promise<AppUpdate | null> {
  const res = await fetch(RELEASES_URL, { headers: { Accept: 'application/vnd.github+json' } })
  if (!res.ok) return null
  const releases: { tag_name: string; name: string; html_url: string; draft: boolean }[] = await res.json()
  const latest = releases
    .filter(r => !r.draft && /^android-v\d+$/.test(r.tag_name))
    .map(r => ({ versionCode: Number(r.tag_name.slice('android-v'.length)), name: r.name, url: r.html_url }))
    .sort((a, b) => b.versionCode - a.versionCode)[0]
  return latest && latest.versionCode > currentVersionCode ? latest : null
}
