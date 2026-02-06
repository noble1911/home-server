import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useUserStore } from '../stores/userStore'
import { useSettingsStore } from '../stores/settingsStore'
import { useConversationStore } from '../stores/conversationStore'
import { api, clearUserFacts, deleteUserAccount } from '../services/api'
import ConfirmDialog from '../components/ConfirmDialog'
import type { AdminUser, InviteCode, OAuthConnection, ToolPermission } from '../types/user'
import { PERMISSION_INFO } from '../types/user'

interface ConnectionsResponse {
  connections: OAuthConnection[]
}

interface AuthorizeResponse {
  authorizeUrl: string
}

interface InviteCodeListResponse {
  codes: InviteCode[]
}

interface CreateInviteCodeResponse {
  code: string
  expiresAt: string
}

interface AdminUserListResponse {
  users: AdminUser[]
}

export default function Settings() {
  const { logout, role } = useAuthStore()
  const { profile, updateButlerName, updateSoul, clearAllFacts, clearProfile, isLoading } = useUserStore()
  const { voiceMode, setVoiceMode } = useSettingsStore()
  const { clearMessages } = useConversationStore()
  const isAdmin = role === 'admin'

  const [connections, setConnections] = useState<OAuthConnection[]>([])
  const [connectionsLoading, setConnectionsLoading] = useState(true)
  const [oauthMessage, setOauthMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Invite code state (admin only)
  const [inviteCodes, setInviteCodes] = useState<InviteCode[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [copiedCode, setCopiedCode] = useState<string | null>(null)

  // Permission management state (admin only)
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([])
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [permSaving, setPermSaving] = useState(false)

  // Deletion state
  const [showClearFactsConfirm, setShowClearFactsConfirm] = useState(false)
  const [showDeleteAccountConfirm, setShowDeleteAccountConfirm] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Fetch OAuth connections on mount
  useEffect(() => {
    fetchConnections()
  }, [])

  // Fetch invite codes and user list on mount (admin only)
  useEffect(() => {
    if (isAdmin) {
      fetchInviteCodes()
      fetchAdminUsers()
    }
  }, [isAdmin])

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

  async function fetchInviteCodes() {
    try {
      const data = await api.get<InviteCodeListResponse>('/admin/invite-codes')
      setInviteCodes(data.codes)
    } catch {
      setInviteCodes([])
    }
  }

  async function generateInviteCode() {
    setIsGenerating(true)
    try {
      const data = await api.post<CreateInviteCodeResponse>('/admin/invite-codes')
      // Re-fetch the full list to get complete status info
      await fetchInviteCodes()
      // Auto-copy the new code
      await copyCode(data.code)
    } catch {
      // Silently fail — admin can retry
    } finally {
      setIsGenerating(false)
    }
  }

  async function revokeInviteCode(code: string) {
    try {
      await api.delete(`/admin/invite-codes/${code}`)
      setInviteCodes(prev => prev.filter(c => c.code !== code))
    } catch {
      // Silently fail
    }
  }

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      setCopiedCode(code)
      setTimeout(() => setCopiedCode(null), 2000)
    } catch {
      // Clipboard API not available
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

  async function fetchAdminUsers() {
    try {
      const data = await api.get<AdminUserListResponse>('/admin/users')
      setAdminUsers(data.users)
    } catch {
      setAdminUsers([])
    }
  }

  async function togglePermission(userId: string, perm: ToolPermission) {
    const user = adminUsers.find(u => u.id === userId)
    if (!user) return

    const has = user.permissions.includes(perm)
    const updated = has
      ? user.permissions.filter(p => p !== perm)
      : [...user.permissions, perm]

    // Optimistic update
    setAdminUsers(prev =>
      prev.map(u => u.id === userId ? { ...u, permissions: updated } : u)
    )

    setPermSaving(true)
    try {
      await api.put(`/admin/users/${userId}/permissions`, { permissions: updated })
    } catch {
      // Revert on error
      setAdminUsers(prev =>
        prev.map(u => u.id === userId ? { ...u, permissions: user.permissions } : u)
      )
    } finally {
      setPermSaving(false)
    }
  }

  async function handleClearFacts() {
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await clearUserFacts()
      clearAllFacts()
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Failed to clear facts')
    } finally {
      setIsDeleting(false)
      setShowClearFactsConfirm(false)
    }
  }

  async function handleDeleteAccount() {
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await deleteUserAccount()
      clearMessages()
      clearProfile()
      logout()
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Failed to delete account')
      setIsDeleting(false)
      setShowDeleteAccountConfirm(false)
    }
  }

  const selectedUser = adminUsers.find(u => u.id === selectedUserId)
  const allPermissions = Object.keys(PERMISSION_INFO) as ToolPermission[]

  const googleConnection = connections.find(c => c.provider === 'google')

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
          {isAdmin && (
            <div>
              <label className="block text-sm text-butler-300 mb-1">Role</label>
              <div className="text-accent text-sm">Admin</div>
            </div>
          )}
        </div>
      </section>

      {/* Invite Codes - admin only */}
      {isAdmin && (
        <section className="card p-4">
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
            Invite Codes
            <span className="text-butler-600 ml-2 text-xs normal-case">admin</span>
          </h2>

          <button
            onClick={generateInviteCode}
            disabled={isGenerating}
            className="btn btn-primary w-full mb-4 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? 'Generating...' : 'Generate Invite Code'}
          </button>

          {inviteCodes.length === 0 ? (
            <p className="text-sm text-butler-500 text-center">
              No invite codes yet. Generate one to add household members.
            </p>
          ) : (
            <div className="space-y-2">
              {inviteCodes.map(code => (
                <div
                  key={code.code}
                  className="flex items-center justify-between p-3 bg-butler-800 rounded-lg"
                >
                  <div className="min-w-0">
                    <span className="font-mono text-butler-100 text-sm">{code.code}</span>
                    <div className="text-xs text-butler-500 mt-0.5">
                      {code.isUsed
                        ? `Used${code.usedBy ? ` by ${code.usedBy.replace('invite_', '')}` : ''}`
                        : code.isExpired
                          ? 'Expired'
                          : `Expires ${new Date(code.expiresAt).toLocaleDateString()}`
                      }
                    </div>
                  </div>
                  <div className="flex gap-2 shrink-0 ml-2">
                    {!code.isUsed && !code.isExpired && (
                      <>
                        <button
                          onClick={() => copyCode(code.code)}
                          className="px-2 py-1 rounded text-xs bg-butler-700 text-accent hover:bg-butler-600"
                        >
                          {copiedCode === code.code ? 'Copied!' : 'Copy'}
                        </button>
                        <button
                          onClick={() => revokeInviteCode(code.code)}
                          className="px-2 py-1 rounded text-xs bg-red-900/50 text-red-300 hover:bg-red-900"
                        >
                          Revoke
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

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
          {/* Google (Calendar + Gmail) */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-butler-100">Google</div>
              {connectionsLoading ? (
                <div className="text-xs text-butler-500">Checking...</div>
              ) : googleConnection ? (
                <div className="text-xs text-butler-400">
                  Connected{googleConnection.accountId ? ` as ${googleConnection.accountId}` : ''} &middot; Calendar, Gmail
                </div>
              ) : (
                <div className="text-xs text-butler-500">Not connected &middot; Calendar, Gmail</div>
              )}
            </div>
            {!connectionsLoading && (
              googleConnection ? (
                <button
                  onClick={() => disconnectProvider('google')}
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

      {/* Your Tool Access - read-only view of permissions */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          Tool Access
          <span className="text-butler-600 ml-2 text-xs normal-case">synced</span>
        </h2>
        <p className="text-xs text-butler-500 mb-3">
          Tools your Butler can use on your behalf. {!isAdmin && 'Ask an admin to change these.'}
        </p>
        <div className="flex flex-wrap gap-2">
          {allPermissions.map(perm => {
            const info = PERMISSION_INFO[perm]
            const enabled = profile.permissions?.includes(perm)
            return (
              <div
                key={perm}
                className={`px-3 py-1.5 rounded-lg text-xs ${
                  enabled
                    ? 'bg-accent/20 text-accent border border-accent/30'
                    : 'bg-butler-800 text-butler-500 border border-butler-700'
                }`}
                title={info.description}
              >
                {info.label}
              </div>
            )
          })}
        </div>
      </section>

      {/* Manage Permissions - admin only */}
      {isAdmin && (
        <section className="card p-4">
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
            Manage Permissions
            <span className="text-butler-600 ml-2 text-xs normal-case">admin</span>
            {permSaving && <span className="text-accent ml-2 text-xs normal-case">saving...</span>}
          </h2>

          {adminUsers.length === 0 ? (
            <p className="text-sm text-butler-500 text-center">Loading users...</p>
          ) : (
            <>
              <div className="mb-4">
                <label className="block text-sm text-butler-300 mb-2">Select User</label>
                <select
                  value={selectedUserId || ''}
                  onChange={(e) => setSelectedUserId(e.target.value || null)}
                  className="input w-full"
                >
                  <option value="">Choose a user...</option>
                  {adminUsers.map(u => (
                    <option key={u.id} value={u.id}>
                      {u.name} {u.role === 'admin' ? '(admin)' : ''}
                    </option>
                  ))}
                </select>
              </div>

              {selectedUser && (
                <div className="space-y-2">
                  {allPermissions.map(perm => {
                    const info = PERMISSION_INFO[perm]
                    const enabled = selectedUser.permissions.includes(perm)
                    return (
                      <button
                        key={perm}
                        onClick={() => togglePermission(selectedUser.id, perm)}
                        className="w-full flex items-center justify-between p-3 bg-butler-800 rounded-lg hover:bg-butler-700 transition-colors"
                      >
                        <div className="text-left">
                          <div className="text-sm text-butler-100">{info.label}</div>
                          <div className="text-xs text-butler-500">{info.description}</div>
                        </div>
                        <div className={`w-10 h-6 rounded-full relative transition-colors ${
                          enabled ? 'bg-accent' : 'bg-butler-600'
                        }`}>
                          <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                            enabled ? 'translate-x-5' : 'translate-x-1'
                          }`} />
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </section>
      )}

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

      {/* Data Management */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          Data Management
        </h2>

        {deleteError && (
          <div className="text-sm mb-3 p-2 rounded bg-red-900/30 text-red-300">
            {deleteError}
          </div>
        )}

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-butler-100">Clear Facts</div>
              <div className="text-xs text-butler-500">
                Remove all learned facts ({profile.facts.length})
              </div>
            </div>
            <button
              onClick={() => setShowClearFactsConfirm(true)}
              disabled={profile.facts.length === 0}
              className="px-3 py-1.5 rounded-lg text-xs bg-red-900/50 text-red-300 hover:bg-red-900 hover:text-red-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Clear
            </button>
          </div>

          <div className="border-t border-butler-700" />

          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-butler-100">Delete Account</div>
              <div className="text-xs text-butler-500">
                Permanently remove your account and all data
              </div>
            </div>
            <button
              onClick={() => setShowDeleteAccountConfirm(true)}
              className="px-3 py-1.5 rounded-lg text-xs bg-red-900/50 text-red-300 hover:bg-red-900 hover:text-red-200"
            >
              Delete
            </button>
          </div>
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

      <ConfirmDialog
        open={showClearFactsConfirm}
        title="Clear All Facts"
        description="This will permanently delete all learned facts about you. Butler will no longer remember your preferences, routines, or personal details. This cannot be undone."
        confirmLabel={isDeleting ? 'Clearing...' : 'Clear All Facts'}
        onConfirm={handleClearFacts}
        onCancel={() => setShowClearFactsConfirm(false)}
      />

      <ConfirmDialog
        open={showDeleteAccountConfirm}
        title="Delete Account"
        description="This will permanently delete your account, conversation history, facts, connected services, and all associated data. You will be signed out immediately. This action cannot be undone."
        confirmLabel={isDeleting ? 'Deleting...' : 'Delete My Account'}
        onConfirm={handleDeleteAccount}
        onCancel={() => setShowDeleteAccountConfirm(false)}
      />
    </div>
  )
}
