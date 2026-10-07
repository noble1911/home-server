import { useCallback, useEffect, useState } from 'react'
import { api } from '../../services/api'
import {
  ButlerNotifications,
  disablePhoneNotifications,
  enablePhoneNotifications,
  type PhoneNotificationStatus,
} from '../../native/butlerNative'

/**
 * Notifications in the Android app: Butler pushes them over the app's own
 * connection (no Firebase). Shown instead of the browser push settings.
 */
export default function PhoneNotifications() {
  const [status, setStatus] = useState<PhoneNotificationStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ type: 'error' | 'ok'; text: string } | null>(null)

  const refresh = useCallback(async () => {
    try {
      setStatus(await ButlerNotifications.status())
    } catch {
      // plugin unavailable: leave the last known status
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 4000)
    const onVisible = () => { if (document.visibilityState === 'visible') refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refresh])

  async function run(action: () => Promise<unknown>, ok?: string) {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      if (ok) setMessage({ type: 'ok', text: ok })
    } catch (err) {
      setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Something went wrong' })
    } finally {
      setBusy(false)
      refresh()
    }
  }

  if (!status) {
    return <p className="text-sm text-butler-500">Checking…</p>
  }

  if (!status.enabled) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-butler-400">
          Get reminders, alerts and approval requests on this phone straight from your home server,
          even when Butler is closed.
        </p>
        <button
          onClick={() => run(enablePhoneNotifications, 'Notifications are on')}
          disabled={busy}
          className="w-full btn bg-accent text-white hover:bg-accent/80 text-sm disabled:opacity-50"
        >
          {busy ? 'Turning on…' : 'Turn on notifications'}
        </button>
        {message && <Note message={message} />}
      </div>
    )
  }

  const state = status.connected
    ? { label: 'Connected', dot: 'bg-green-400' }
    : { label: status.lastError ? `Reconnecting (${status.lastError})` : 'Connecting…', dot: 'bg-amber-400' }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm">
        <span className={`inline-block w-2 h-2 rounded-full ${state.dot}`} aria-hidden />
        <span className="text-butler-100">{state.label}</span>
      </div>

      {!status.notificationsAllowed && (
        <Warning
          text="Android is blocking Butler's notifications."
          action="Allow"
          onClick={() => run(() => ButlerNotifications.openNotificationSettings())}
        />
      )}
      {status.batteryOptimized && (
        <Warning
          text="Battery optimisation can cut Butler's connection while the phone sleeps."
          action="Allow in background"
          onClick={() => run(() => ButlerNotifications.openBatterySettings())}
        />
      )}

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={() => run(() => api.post('/push/test'), 'Test sent — it should arrive in a moment')}
          disabled={busy}
          className="btn bg-butler-700 text-butler-300 hover:bg-butler-600 text-sm disabled:opacity-50"
        >
          Send test
        </button>
        <button
          onClick={() => run(() => ButlerNotifications.openNotificationSettings())}
          className="btn bg-butler-700 text-butler-300 hover:bg-butler-600 text-sm"
        >
          Notification types
        </button>
      </div>
      <p className="text-xs text-butler-500">
        Each kind (reminders, alerts, downloads…) is its own Android channel, so you can change its
        sound or turn it off. The "Butler connection" one just keeps the link open — you can hide it.
      </p>

      <button
        onClick={() => run(() => disablePhoneNotifications(), 'Notifications are off on this phone')}
        disabled={busy}
        className="w-full btn bg-red-900/50 text-red-300 hover:bg-red-900 hover:text-red-200 text-sm disabled:opacity-50"
      >
        Turn off on this phone
      </button>
      {message && <Note message={message} />}
    </div>
  )
}

function Warning({ text, action, onClick }: { text: string; action: string; onClick: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-700/50 bg-amber-900/20 px-3 py-2">
      <span className="text-xs text-amber-200">{text}</span>
      <button onClick={onClick} className="shrink-0 px-3 py-1.5 rounded-lg text-xs bg-amber-600 text-white hover:bg-amber-500">
        {action}
      </button>
    </div>
  )
}

function Note({ message }: { message: { type: 'error' | 'ok'; text: string } }) {
  return (
    <p className={`text-xs ${message.type === 'error' ? 'text-red-400' : 'text-green-400'}`} role="status">
      {message.text}
    </p>
  )
}
