# Butler for Android

A native Android app for Butler with proper notifications: they arrive within
seconds with the app closed and the phone locked, each kind has its own Android
channel, and tapping one opens the right screen. **No Firebase or Google
account is involved**: Butler delivers notifications itself.

## Install

1. On the phone, open the latest **Butler Android build** release:
   <https://github.com/noble1911/home-server/releases> (tags `android-v<N>`).
2. Download the `.apk` and open it. Android asks to allow your browser to
   install apps the first time — allow it.
3. Open Butler and sign in as usual.

**Updates:** Settings → About shows *Update available* when a newer build is
released; tap it and install over the top. Most changes don't need an update at
all: the app shows the live site (butler.noblehaus.uk), so web changes appear as
soon as they're deployed. Only native changes (notifications, icons) need a new
build.

## Turn on notifications

Settings → **Notifications · this phone** → **Turn on notifications**, then:

- **Allow notifications** when Android asks.
- **Allow in background** (the yellow prompt): exempts Butler from battery
  optimisation. Without it, Android cuts the connection when the phone sleeps
  and notifications arrive late.
- **Notification types** opens Android's per-channel settings: Approvals,
  Reminders, Server alerts, Calendar, Downloads, Smart home, Weather, General.
  Set sounds or turn kinds off there.
- The always-there **"Butler connection"** notification is how Android lets an
  app keep a connection open. Long-press it → turn off *Butler connection* to
  hide it; notifications keep working.

Butler also follows Settings → Notifications (WhatsApp section): switched-off
categories aren't sent, and during **quiet hours** notifications still arrive
but silently. Approvals and test notifications always ring.

## How it works

```
Butler (api/push.py: send_push_to_user)
  ├─ preferences: skip / silent (quiet hours) / send
  ├─ browsers ─ Web Push (VAPID) ─▶ PWA service worker
  └─ app ─ butler.notifications (outbox) ─▶ open WebSocket ─▶ phone
                                   │
phone: NotificationService (foreground service)
  └─ wss://butler.noblehaus.uk/api/notifications/ws?since=<last id>
       Authorization: Device <token>      (nginx → butler-api, Cloudflare tunnel)
```

- **Device credential:** turning notifications on registers the phone
  (`POST /api/devices`) and gets a token only for the notification socket
  (stored as a SHA-256 in `butler.devices`). It's separate from the login
  tokens, so the background connection can't interfere with the app's session.
  Turning off or signing out deletes it.
- **Outbox:** every notification for a user with an active phone is stored in
  `butler.notifications` (kept 7 days). The phone sends the last id it showed
  when it connects, so anything sent while it was offline arrives on reconnect.
- **Keeping the connection alive:** OkHttp pings every 30 s and Butler sends a
  keepalive every 45 s (Cloudflare drops idle connections after 100 s). On a
  drop the app retries after 2 s, backing off to 5 min, and immediately when
  the network comes back. It restarts after a reboot or an app update.
- **Fallbacks:** a phone counts as reachable if it connected in the last 7
  days, so scheduled tasks don't also send WhatsApp just because it's briefly
  offline.
- **Google:** Google blocks sign-in inside app web views, so *Connect Google*
  opens the system browser; the flow ends on a "go back to the Butler app" page.

Code: `app/android/` (Capacitor 8 project; native code in
`app/android/app/src/main/java/uk/noblehaus/butler/`), the web bridge in
`app/src/native/butlerNative.ts`, server side in `butler/api/devices.py`,
`butler/api/routes/devices.py`, `butler/api/push.py`.

## Building a release

GitHub → **Actions → Build Android app → Run workflow** (on `main`). It builds a
signed APK and publishes the `android-v<run number>` release that phones update
from. Nothing builds automatically.

### Signing key

Android only installs an update if it's signed with the same key as the
installed app, so the key must never change. It lives in four repository
secrets (`ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS` = `butler`, `ANDROID_KEY_PASSWORD`) and is backed up in Ron's
MacBook login Keychain:

```bash
# Re-create the secrets from the Keychain backup
security find-generic-password -a noble1911 -s "Butler Android release keystore (base64, alias butler)" -w \
  | gh secret set ANDROID_KEYSTORE_BASE64 -R noble1911/home-server
PW=$(security find-generic-password -a noble1911 -s "Butler Android release keystore password" -w)
printf %s "$PW" | gh secret set ANDROID_KEYSTORE_PASSWORD -R noble1911/home-server
printf %s "$PW" | gh secret set ANDROID_KEY_PASSWORD -R noble1911/home-server
printf butler   | gh secret set ANDROID_KEY_ALIAS -R noble1911/home-server
```

If the key is ever lost, make a new one, and everyone uninstalls and reinstalls
the app once.

### Local build

Needs JDK 21 and the Android SDK (`~/Library/Android/sdk`).

```bash
cd app
npm ci && npm run build && npx cap sync android
cd android && JAVA_HOME=<jdk 21> ./gradlew assembleDebug   # app/build/outputs/apk/debug/
```

## Testing

Debug builds allow plain HTTP to `10.0.2.2` (the host, from the emulator), so
the notification service can be tested against `app/android/dev/mock-notify-server.py`
without touching the real server:

```bash
python app/android/dev/mock-notify-server.py 8765 5 8   # start at id 5, drop each connection after 8 s
adb install -r app/android/app/build/outputs/apk/debug/app-debug.apk
adb shell pm grant uk.noblehaus.butler android.permission.POST_NOTIFICATIONS
# point the service at the mock (debug builds allow run-as):
adb shell "run-as uk.noblehaus.butler sh -c 'mkdir -p shared_prefs && cat > shared_prefs/butler_notifications.xml'" <<'EOF'
<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map><boolean name="enabled" value="true" /><string name="baseUrl">http://10.0.2.2:8765</string>
<string name="token">test-token</string><string name="deviceId">emu-1</string><long name="sinceId" value="5" /></map>
EOF
adb shell am start -n uk.noblehaus.butler/.MainActivity     # once: leaves Android's "stopped" state
adb install -r app/android/app/build/outputs/apk/debug/app-debug.apk   # MY_PACKAGE_REPLACED starts the service
adb shell dumpsys notification --noredact | grep -A3 uk.noblehaus.butler
```

The WebView can be inspected from Chrome (`chrome://inspect`) or over
`adb forward tcp:9333 localabstract:webview_devtools_remote_<pid>`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Notifications arrive late or only when the app is opened | Settings → Notifications → **Allow in background** (battery optimisation). Some phones (Samsung, Xiaomi) also need Butler set to *Unrestricted* in their own battery settings |
| Status says *Reconnecting (not authorised…)* | The device was removed on the server: turn notifications off and on again |
| *Connect Google* does nothing | It opens the system browser; finish there, then come back to the app |
| "App not installed" when updating | The APK was signed with a different key (see Signing key) — uninstall, then install |
