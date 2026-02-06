import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useUserStore } from '../stores/userStore'
import { useSettingsStore } from '../stores/settingsStore'
import { api } from '../services/api'
import type { OAuthConnection } from '../types/user'

interface ConnectionsResponse {
  connections: OAuthConnection[]
}

interface AuthorizeResponse {
  authorizeUrl: string
}

export default function Settings() {
  const { logout } = useAuthStore()
  const { profile, updateButlerName, updateSoul, isLoading } = useUserStore()
  const { voiceMode, setVoiceMode } = useSettingsStore()

  const [connections, setConnections] = useState<OAuthConnection[]>([])
  const [connectionsLoading, setConnectionsLoading] = useState(true)
  const [oauthMessage, setOauthMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Fetch OAuth connections on mount
  useEffect(() => {
    fetchConnections()
  }, [])

  // Handle OAuth callback redirect params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const oauthProvider = params.get('oauth')
    const status = params.get('status')
    if (oauthProvider && status) {
      if (status === 'success') {
        setOauthMessage({ type: 'success', text: `${oauthProvider} connected successfully!` })
      } else {
        const message = params.get('message') || 'Connection failed'
        setOauthMessage({ type: 'error', text: `${oauthProvider}: ${message}` })
      }
      // Clean up URL params
      window.history.replaceState({}, '', '/settings')
      // Refresh connections
      fetchConnections()
    }
  }, [])

  async function fetchConnections() {
    try {
      const data = await api.get<ConnectionsResponse>('/oauth/connections')
      setConnections(data.connections)
    } catch {
      // OAuth not configured or server error — silently show empty
      setConnections([])
    } finally {
      setConnectionsLoading(false)
    }
  }

  async function connectGoogle() {
    try {
      const data = await api.get<AuthorizeResponse>('/oauth/google/authorize')
      window.location.href = data.authorizeUrl
    } catch {
      setOauthMessage({ type: 'error', text: 'Failed to start Google connection. Is OAuth configured?' })
    }
  }

  async function disconnectProvider(provider: string) {
    try {
      await api.delete(`/oauth/${provider}`)
      setConnections(prev => prev.filter(c => c.provider !== provider))
      setOauthMessage({ type: 'success', text: 'Disconnected successfully.' })
    } catch {
      setOauthMessage({ type: 'error', text: 'Failed to disconnect.' })
    }
  }

  const googleConnection = connections.find(c => c.provider === 'google_calendar')

  if (!profile) {
    return (
      <div className="p-4 flex items-center justify-center min-h-[50vh]">
        <div className="text-butler-400">Loading profile...</div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-butler-100">Settings</h1>
        <p className="text-sm text-butler-400">Customize your Butler experience</p>
        {isLoading && (
          <p className="text-xs text-accent mt-1">Syncing...</p>
        )}
      </div>

      {/* Account - synced across devices */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          Account
          <span className="text-butler-600 ml-2 text-xs normal-case">synced</span>
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-butler-300 mb-1">Name</label>
            <div className="text-butler-100">{profile.name}</div>
          </div>
        </div>
      </section>

      {/* Butler Settings - synced across devices */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          My Butler
          <span className="text-butler-600 ml-2 text-xs normal-case">synced</span>
        </h2>
        <div className="space-y-4">
          <div>
            <label htmlFor="butler-name" className="block text-sm text-butler-300 mb-1">
              Butler Name
            </label>
            <input
              id="butler-name"
              type="text"
              value={profile.butlerName}
              onChange={(e) => updateButlerName(e.target.value)}
              className="input"
            />
          </div>
        </div>
      </section>

      {/* Personality - synced across devices */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          Personality
          <span className="text-butler-600 ml-2 text-xs normal-case">synced</span>
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-butler-300 mb-2">Style</label>
            <div className="flex flex-wrap gap-2">
              {(['casual', 'balanced', 'formal'] as const).map(style => (
                <button
                  key={style}
                  onClick={() => updateSoul({ personality: style })}
                  className={`px-4 py-2 rounded-lg text-sm capitalize ${
                    profile.soul.personality === style
                      ? 'bg-accent text-white'
                      : 'bg-butler-700 text-butler-300 hover:bg-butler-600'
                  }`}
                >
                  {style}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm text-butler-300 mb-2">Verbosity</label>
            <div className="flex flex-wrap gap-2">
              {(['concise', 'moderate', 'detailed'] as const).map(level => (
                <button
                  key={level}
                  onClick={() => updateSoul({ verbosity: level })}
                  className={`px-4 py-2 rounded-lg text-sm capitalize ${
                    profile.soul.verbosity === level
                      ? 'bg-accent text-white'
                      : 'bg-butler-700 text-butler-300 hover:bg-butler-600'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm text-butler-300 mb-2">Humor</label>
            <div className="flex flex-wrap gap-2">
              {(['none', 'subtle', 'playful'] as const).map(level => (
                <button
                  key={level}
                  onClick={() => updateSoul({ humor: level })}
                  className={`px-4 py-2 rounded-lg text-sm capitalize ${
                    profile.soul.humor === level
                      ? 'bg-accent text-white'
                      : 'bg-butler-700 text-butler-300 hover:bg-butler-600'
                  }`}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Connected Services */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          Connected Services
          <span className="text-butler-600 ml-2 text-xs normal-case">synced</span>
        </h2>

        {oauthMessage && (
          <div className={`text-sm mb-3 p-2 rounded ${
            oauthMessage.type === 'success'
              ? 'bg-green-900/30 text-green-300'
              : 'bg-red-900/30 text-red-300'
          }`}>
            {oauthMessage.text}
          </div>
        )}

        <div className="space-y-3">
          {/* Google Calendar */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-butler-100">Google Calendar</div>
              {connectionsLoading ? (
                <div className="text-xs text-butler-500">Checking...</div>
              ) : googleConnection ? (
                <div className="text-xs text-butler-400">
                  Connected{googleConnection.accountId ? ` as ${googleConnection.accountId}` : ''}
                </div>
              ) : (
                <div className="text-xs text-butler-500">Not connected</div>
              )}
            </div>
            {!connectionsLoading && (
              googleConnection ? (
                <button
                  onClick={() => disconnectProvider('google_calendar')}
                  className="px-3 py-1.5 rounded-lg text-xs bg-red-900/50 text-red-300 hover:bg-red-900 hover:text-red-200"
                >
                  Disconnect
                </button>
              ) : (
                <button
                  onClick={connectGoogle}
                  className="px-3 py-1.5 rounded-lg text-xs bg-accent text-white hover:bg-accent/80"
                >
                  Connect
                </button>
              )
            )}
          </div>
        </div>
      </section>

      {/* Device Settings - local to this device */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          This Device
          <span className="text-butler-600 ml-2 text-xs normal-case">local only</span>
        </h2>
        <div>
          <label className="block text-sm text-butler-300 mb-2">Voice Input Mode</label>
          <div className="flex flex-wrap gap-2">
            {([
              { value: 'push-to-talk' as const, label: 'Push to Talk' },
              { value: 'tap-to-toggle' as const, label: 'Tap to Toggle' },
            ]).map(mode => (
              <button
                key={mode.value}
                onClick={() => setVoiceMode(mode.value)}
                className={`px-4 py-2 rounded-lg text-sm ${
                  voiceMode === mode.value
                    ? 'bg-accent text-white'
                    : 'bg-butler-700 text-butler-300 hover:bg-butler-600'
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-butler-500 mt-2">
            This setting only applies to this device.
          </p>
        </div>
      </section>

      {/* About & Logout */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          About
        </h2>
        <div className="space-y-2 text-sm text-butler-400 mb-4">
          <div className="flex justify-between">
            <span>Version</span>
            <span className="text-butler-300">0.1.0</span>
          </div>
        </div>
        <button
          onClick={logout}
          className="w-full btn bg-red-900/50 text-red-300 hover:bg-red-900 hover:text-red-200"
        >
          Sign Out
        </button>
      </section>
    </div>
  )
}
