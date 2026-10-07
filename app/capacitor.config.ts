import type { CapacitorConfig } from '@capacitor/cli'

/**
 * Butler Android app (#214).
 *
 * The app is a native shell around the *live* site: it loads BUTLER_URL, so
 * every web deploy updates the app's UI without a new APK. Native code adds
 * what the browser can't do well: notifications Butler pushes over its own
 * connection (no Firebase), notification channels, and microphone access.
 * `webDir` only holds the fallback bundle Capacitor needs to build.
 */
const butlerUrl = process.env.BUTLER_URL || 'https://butler.noblehaus.uk'

const config: CapacitorConfig = {
  appId: 'uk.noblehaus.butler',
  appName: 'Butler',
  webDir: 'dist',
  server: {
    url: butlerUrl,
    androidScheme: 'https',
    // Everything else (Google sign-in, service links) opens in the browser.
    allowNavigation: [new URL(butlerUrl).host],
  },
  android: {
    allowMixedContent: false,
  },
}

export default config
