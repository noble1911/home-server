import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useUserStore } from '../stores/userStore'
import { useSettingsStore } from '../stores/settingsStore'
import { useConversationStore } from '../stores/conversationStore'
import { usePushNotifications } from '../hooks/usePushNotifications'
import { api, clearUserFacts, deleteUserAccount } from '../services/api'
import ConfirmDialog from '../components/ConfirmDialog'
import type { AdminUser, InviteCode, OAuthConnection, ServiceCredential, ToolPermission } from '../types/user'
import { DEFAULT_VOICE, PERMISSION_INFO, SERVICE_DISPLAY_NAMES, VOICE_OPTIONS } from '../types/user'

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
  permissions: string[]
}

interface AdminUserListResponse {
  users: AdminUser[]
}

export default function Settings() {
  const { logout, role } = useAuthStore()
  const { profile, updateButlerName, updateSoul, updateNotifications, clearAllFacts, clearProfile, isLoading } = useUserStore()
  const { voiceMode, setVoiceMode } = useSettingsStore()
  const { clearMessages } = useConversationStore()
  const push = usePushNotifications()
  const isAdmin = role === 'admin'

  const [connections, setConnections] = useState<OAuthConnection[]>([])
  const [connectionsLoading, setConnectionsLoading] = useState(true)
  const [oauthMessage, setOauthMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Invite code state (admin only)
  const [inviteCodes, setInviteCodes] = useState<InviteCode[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [copiedCode, setCopiedCode] = useState<string | null>(null)
  const [invitePermissions, setInvitePermissions] = useState<Set<ToolPermission>>(
    new Set(['media', 'home'])
  )

  // Permission management state (admin only)
  const [adminUsers, setAdminUsers] = useState<AdminUser[]>([])
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [permSaving, setPermSaving] = useState(false)
  const [showRemoveUserConfirm, setShowRemoveUserConfirm] = useState(false)
  const [isRemovingUser, setIsRemovingUser] = useState(false)
  const [removeUserError, setRemoveUserError] = useState<string | null>(null)
  const [adminReprovisioning, setAdminReprovisioning] = useState(false)
  const [adminReprovisionError, setAdminReprovisionError] = useState<string | null>(null)
  const [adminReprovisionSuccess, setAdminReprovisionSuccess] = useState(false)

  // Service credentials state
  const [serviceCredentials, setServiceCredentials] = useState<ServiceCredential[]>([])
  const [credentialsLoading, setCredentialsLoading] = useState(true)
  const [visiblePasswords, setVisiblePasswords] = useState<Set<string>>(new Set())
  const [isReprovisioning, setIsReprovisioning] = useState(false)
  const [reprovisionError, setReprovisionError] = useState<string | null>(null)

  // Service password change state
  const [newServicePassword, setNewServicePassword] = useState('')
  const [confirmServicePassword, setConfirmServicePassword] = useState('')
  const [passwordChangeLoading, setPasswordChangeLoading] = useState(false)
  const [passwordChangeResults, setPasswordChangeResults] = useState<{ service: string; status: string; error?: string }[] | null>(null)

  // WhatsApp notification state
  const [phoneInput, setPhoneInput] = useState(profile?.phone || '')
  const [phoneError, setPhoneError] = useState<string | null>(null)
  const [whatsappTestResult, setWhatsappTestResult] = useState<string | null>(null)
  const [isSendingWhatsappTest, setIsSendingWhatsappTest] = useState(false)

  // Sync phone input when profile changes externally
  useEffect(() => {
    setPhoneInput(profile?.phone || '')
  }, [profile?.phone])

  // Deletion state
  const [showClearFactsConfirm, setShowClearFactsConfirm] = useState(false)
  const [showDeleteAccountConfirm, setShowDeleteAccountConfirm] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Fetch OAuth connections and service credentials on mount
  useEffect(() => {
    fetchConnections()
    fetchServiceCredentials()
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

  async function fetchServiceCredentials() {
    try {
      const data = await api.get<{ credentials: ServiceCredential[] }>('/user/service-credentials')
      setServiceCredentials(data.credentials)
    } catch {
      setServiceCredentials([])
    } finally {
      setCredentialsLoading(false)
    }
  }

  function togglePasswordVisibility(service: string) {
    setVisiblePasswords(prev => {
      const next = new Set(prev)
      if (next.has(service)) next.delete(service)
      else next.add(service)
      return next
    })
  }

  async function retryProvisioning() {
    setIsReprovisioning(true)
    setReprovisionError(null)
    try {
      await api.post('/user/reprovision')
      await fetchServiceCredentials()
    } catch (err) {
      setReprovisionError(err instanceof Error ? err.message : 'Re-provisioning failed')
    } finally {
      setIsReprovisioning(false)
    }
  }

  async function changeServicePassword() {
    if (newServicePassword !== confirmServicePassword) return
    if (newServicePassword.length < 6) return
    setPasswordChangeLoading(true)
    setPasswordChangeResults(null)
    try {
      const data = await api.put<{ results: { service: string; status: string; error?: string }[] }>(
        '/user/service-password',
        { newPassword: newServicePassword }
      )
      setPasswordChangeResults(data.results)
      setNewServicePassword('')
      setConfirmServicePassword('')
      await fetchServiceCredentials()
    } catch (err) {
      setPasswordChangeResults([{
        service: 'all',
        status: 'failed',
        error: err instanceof Error ? err.message : 'Password change failed',
      }])
    } finally {
      setPasswordChangeLoading(false)
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

  function toggleInvitePermission(perm: ToolPermission) {
    setInvitePermissions(prev => {
      const next = new Set(prev)
      if (next.has(perm)) next.delete(perm)
      else next.add(perm)
      return next
    })
  }

  async function generateInviteCode() {
    setIsGenerating(true)
    try {
      const data = await api.post<CreateInviteCodeResponse>('/admin/invite-codes', {
        permissions: Array.from(invitePermissions),
      })
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
      // Pass our origin so the backend derives the correct redirect URLs
      // (works for LAN, localhost, and Cloudflare Tunnel access)
      const origin = encodeURIComponent(window.location.origin)
      const data = await api.get<AuthorizeResponse>(`/oauth/google/authorize?origin=${origin}`)
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

  async function adminReprovision(userId: string) {
    setAdminReprovisioning(true)
    setAdminReprovisionError(null)
    setAdminReprovisionSuccess(false)
    try {
      await api.post(`/admin/users/${userId}/reprovision`)
      setAdminReprovisionSuccess(true)
      setTimeout(() => setAdminReprovisionSuccess(false), 3000)
    } catch (err) {
      setAdminReprovisionError(err instanceof Error ? err.message : 'Re-provisioning failed')
    } finally {
      setAdminReprovisioning(false)
    }
  }

  async function removeUser(userId: string) {
    setIsRemovingUser(true)
    setRemoveUserError(null)
    try {
      await api.delete(`/admin/users/${userId}`)
      setAdminUsers(prev => prev.filter(u => u.id !== userId))
      setSelectedUserId(null)
      setShowRemoveUserConfirm(false)
      // Refresh invite codes too (user may have been tied to one)
      await fetchInviteCodes()
    } catch (err) {
      setRemoveUserError(err instanceof Error ? err.message : 'Failed to remove user')
    } finally {
      setIsRemovingUser(false)
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

          {/* Change service password */}
          {!credentialsLoading && serviceCredentials.length > 0 && (
            <div className="pt-4 border-t border-butler-700">
              <label className="block text-sm text-butler-300 mb-1">Service Password</label>
              <p className="text-xs text-butler-500 mb-3">
                Change your password across Jellyfin, Audiobookshelf, Nextcloud, and other services.
              </p>
              <div className="space-y-2">
                <input
                  type="password"
                  value={newServicePassword}
                  onChange={(e) => setNewServicePassword(e.target.value)}
                  placeholder="New password (min 6 chars)"
                  className="input w-full text-sm"
                />
                <input
                  type="password"
                  value={confirmServicePassword}
                  onChange={(e) => setConfirmServicePassword(e.target.value)}
                  placeholder="Confirm password"
                  className="input w-full text-sm"
                />
                {newServicePassword && confirmServicePassword && newServicePassword !== confirmServicePassword && (
                  <p className="text-xs text-red-400">Passwords do not match</p>
                )}
                <button
                  onClick={changeServicePassword}
                  disabled={
                    passwordChangeLoading ||
                    !newServicePassword ||
                    newServicePassword.length < 6 ||
                    newServicePassword !== confirmServicePassword
                  }
                  className="w-full btn bg-butler-700 text-butler-300 hover:bg-butler-600 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {passwordChangeLoading ? 'Updating...' : 'Change Password'}
                </button>
              </div>
              {passwordChangeResults && (
                <div className="mt-2 space-y-1">
                  {passwordChangeResults.map(r => (
                    <div key={r.service} className={`text-xs ${r.status === 'updated' ? 'text-green-400' : r.status === 'skipped' ? 'text-butler-500' : 'text-red-400'}`}>
                      {SERVICE_DISPLAY_NAMES[r.service]?.label || r.service}: {r.status}{r.error ? ` — ${r.error}` : ''}
                    </div>
                  ))}
                </div>
              )}
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

          <div className="mb-4 p-3 bg-butler-900 rounded-lg">
            <p className="text-sm font-medium text-butler-300 mb-2">Permissions for new user</p>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(PERMISSION_INFO) as ToolPermission[]).map(perm => (
                <button
                  key={perm}
                  onClick={() => toggleInvitePermission(perm)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    invitePermissions.has(perm)
                      ? 'bg-accent/20 text-accent border border-accent/40'
                      : 'bg-butler-800 text-butler-400 border border-butler-600'
                  }`}
                >
                  {PERMISSION_INFO[perm].label}
                </button>
              ))}
            </div>
          </div>

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
                        ? `Used${code.usedBy ? ` by ${code.usedBy}` : ''}`
                        : code.isExpired
                          ? 'Expired'
                          : `Expires ${new Date(code.expiresAt).toLocaleDateString()}`
                      }
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {code.permissions.map(p => (
                        <span key={p} className="text-xs px-1.5 py-0.5 rounded bg-accent/10 text-accent">
                          {PERMISSION_INFO[p as ToolPermission]?.label || p}
                        </span>
                      ))}
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

          <div>
            <label className="block text-sm text-butler-300 mb-2">Voice</label>
            <div className="space-y-2">
              {VOICE_OPTIONS.map(v => (
                <button
                  key={v.id}
                  onClick={() => updateSoul({ voice: v.id })}
                  className={`w-full p-3 rounded-lg border text-left transition-colors ${
                    (profile.soul.voice || DEFAULT_VOICE) === v.id
                      ? 'border-accent bg-accent/10'
                      : 'border-butler-700 bg-butler-800 hover:border-butler-600'
                  }`}
                >
                  <div className="text-sm text-butler-100">{v.name}</div>
                  <div className="text-xs text-butler-400">{v.accent} {v.gender}</div>
                </button>
              ))}
            </div>
            <p className="text-xs text-butler-500 mt-2">
              Voice changes take effect on your next voice session.
            </p>
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

      {/* My Service Accounts */}
      {!credentialsLoading && serviceCredentials.length > 0 && (
        <section className="card p-4">
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
            My Service Accounts
            <span className="text-butler-600 ml-2 text-xs normal-case">synced</span>
          </h2>
          <p className="text-xs text-butler-500 mb-3">
            Use these credentials to log into apps directly (web UI or mobile app).
          </p>
          <div className="space-y-3">
            {serviceCredentials.map(cred => {
              const info = SERVICE_DISPLAY_NAMES[cred.service] || { label: cred.service, description: '' }
              const showPassword = visiblePasswords.has(cred.service)
              return (
                <div key={cred.service} className="p-3 bg-butler-800 rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <div className="text-sm text-butler-100">{info.label}</div>
                      <div className="text-xs text-butler-500">{info.description}</div>
                    </div>
                    {cred.status === 'failed' && (
                      <span className="px-2 py-0.5 rounded text-xs bg-red-900/50 text-red-300">Failed</span>
                    )}
                  </div>
                  {cred.status === 'active' && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-butler-400">Username</span>
                        <span className="font-mono text-xs text-butler-200">{cred.username}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-butler-400">Password</span>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-butler-200">
                            {showPassword ? cred.password : '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'}
                          </span>
                          <button
                            onClick={() => togglePasswordVisibility(cred.service)}
                            className="text-xs text-accent hover:text-accent/80"
                          >
                            {showPassword ? 'Hide' : 'Show'}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                  {cred.status === 'failed' && cred.errorMessage && (
                    <div className="text-xs text-red-400 mt-1">{cred.errorMessage}</div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Retry failed services */}
          {serviceCredentials.some(c => c.status === 'failed') && (
            <div className="mt-4">
              {reprovisionError && (
                <div className="text-xs text-red-400 mb-2">{reprovisionError}</div>
              )}
              <button
                onClick={retryProvisioning}
                disabled={isReprovisioning}
                className="w-full btn bg-accent/20 text-accent hover:bg-accent/30 text-sm disabled:opacity-50"
              >
                {isReprovisioning ? 'Retrying...' : 'Retry Failed Services'}
              </button>
            </div>
          )}

        </section>
      )}

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

                  {selectedUser.role !== 'admin' && (
                    <div className="pt-3 mt-3 border-t border-butler-700 space-y-2">
                      {adminReprovisionError && (
                        <div className="text-xs text-red-400">{adminReprovisionError}</div>
                      )}
                      {adminReprovisionSuccess && (
                        <div className="text-xs text-green-400">Services re-provisioned successfully</div>
                      )}
                      <button
                        onClick={() => adminReprovision(selectedUser.id)}
                        disabled={adminReprovisioning}
                        className="w-full btn bg-accent/20 text-accent hover:bg-accent/30 text-sm disabled:opacity-50"
                      >
                        {adminReprovisioning ? 'Provisioning...' : 'Reprovision Services'}
                      </button>
                      {removeUserError && (
                        <div className="text-xs text-red-400">{removeUserError}</div>
                      )}
                      <button
                        onClick={() => setShowRemoveUserConfirm(true)}
                        className="w-full btn bg-red-900/50 text-red-300 hover:bg-red-900 hover:text-red-200 text-sm"
                      >
                        Remove User
                      </button>
                    </div>
                  )}
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

      {/* Push Notifications - per device */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          Push Notifications
          <span className="text-butler-600 ml-2 text-xs normal-case">this device</span>
        </h2>

        {!push.isSupported ? (
          <p className="text-sm text-butler-500">
            Push notifications are not supported in this browser.
          </p>
        ) : push.permission === 'denied' ? (
          <p className="text-sm text-butler-500">
            Notifications are blocked. Enable them in your browser settings to receive push notifications.
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-butler-100">
                  {push.isSubscribed ? 'Enabled' : 'Disabled'}
                </div>
                <div className="text-xs text-butler-500">
                  {push.isSubscribed
                    ? 'You will receive notifications from Butler'
                    : 'Enable to receive alerts when the app is closed'}
                </div>
              </div>
              <button
                onClick={push.isSubscribed ? push.unsubscribe : push.subscribe}
                disabled={push.isLoading}
                className={`px-3 py-1.5 rounded-lg text-xs disabled:opacity-50 ${
                  push.isSubscribed
                    ? 'bg-red-900/50 text-red-300 hover:bg-red-900 hover:text-red-200'
                    : 'bg-accent text-white hover:bg-accent/80'
                }`}
              >
                {push.isLoading
                  ? 'Loading...'
                  : push.isSubscribed
                    ? 'Disable'
                    : 'Enable'}
              </button>
            </div>

            {push.isSubscribed && (
              <button
                onClick={push.sendTest}
                className="w-full btn bg-butler-700 text-butler-300 hover:bg-butler-600 text-sm"
              >
                Send Test Notification
              </button>
            )}
          </div>
        )}
      </section>

      {/* WhatsApp Notifications - synced */}
      <section className="card p-4">
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-4">
          WhatsApp Notifications
          <span className="text-butler-600 ml-2 text-xs normal-case">synced</span>
        </h2>

        <div className="space-y-4">
          {/* Phone number */}
          <div>
            <label htmlFor="whatsapp-phone" className="block text-sm text-butler-300 mb-1">
              Phone Number
            </label>
            <input
              id="whatsapp-phone"
              type="tel"
              value={phoneInput}
              onChange={(e) => { setPhoneInput(e.target.value); setPhoneError(null) }}
              onBlur={() => {
                if (phoneInput && !/^\+[1-9]\d{1,14}$/.test(phoneInput)) {
                  setPhoneError('Use international format: +447123456789')
                  return
                }
                setPhoneError(null)
                if (phoneInput !== (profile?.phone || '')) {
                  updateNotifications(phoneInput)
                }
              }}
              placeholder="+447123456789"
              className="input"
            />
            {phoneError && (
              <p className="text-xs text-red-400 mt-1">{phoneError}</p>
            )}
            <p className="text-xs text-butler-500 mt-1">
              International format with country code (E.164)
            </p>
          </div>

          {/* Master toggle */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-butler-100">Notifications</div>
              <div className="text-xs text-butler-500">
                {profile?.notificationPrefs.enabled ? 'Receiving WhatsApp alerts' : 'WhatsApp alerts are paused'}
              </div>
            </div>
            <button
              onClick={() => updateNotifications(undefined, { enabled: !profile?.notificationPrefs.enabled })}
              className="relative"
            >
              <div className={`w-10 h-6 rounded-full transition-colors ${
                profile?.notificationPrefs.enabled ? 'bg-accent' : 'bg-butler-600'
              }`}>
                <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                  profile?.notificationPrefs.enabled ? 'translate-x-5' : 'translate-x-1'
                }`} />
              </div>
            </button>
          </div>

          {/* Category toggles */}
          {profile?.notificationPrefs.enabled && (
            <div className="space-y-2">
              <label className="block text-sm text-butler-300 mb-1">Categories</label>
              {(['download', 'reminder', 'weather', 'smart_home', 'calendar', 'general'] as const).map(cat => {
                const isOn = profile.notificationPrefs.categories.includes(cat)
                return (
                  <button
                    key={cat}
                    onClick={() => {
                      const current = profile.notificationPrefs.categories
                      const updated = isOn
                        ? current.filter(c => c !== cat)
                        : [...current, cat]
                      updateNotifications(undefined, { categories: updated })
                    }}
                    className="w-full flex items-center justify-between p-3 bg-butler-800 rounded-lg hover:bg-butler-700 transition-colors"
                  >
                    <span className="text-sm text-butler-100 capitalize">{cat.replace('_', ' ')}</span>
                    <div className={`w-10 h-6 rounded-full relative transition-colors ${
                      isOn ? 'bg-accent' : 'bg-butler-600'
                    }`}>
                      <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                        isOn ? 'translate-x-5' : 'translate-x-1'
                      }`} />
                    </div>
                  </button>
                )
              })}
            </div>
          )}

          {/* Test button */}
          {profile?.phone && profile.notificationPrefs.enabled && (
            <button
              onClick={async () => {
                setIsSendingWhatsappTest(true)
                setWhatsappTestResult(null)
                try {
                  const data = await api.post<{ result: string }>('/user/notifications/test')
                  setWhatsappTestResult(data.result)
                } catch {
                  setWhatsappTestResult('Failed to send test message')
                } finally {
                  setIsSendingWhatsappTest(false)
                }
              }}
              disabled={isSendingWhatsappTest}
              className="w-full btn bg-butler-700 text-butler-300 hover:bg-butler-600 text-sm disabled:opacity-50"
            >
              {isSendingWhatsappTest ? 'Sending...' : 'Send Test Message'}
            </button>
          )}

          {whatsappTestResult && (
            <p className={`text-xs ${/error|failed/i.test(whatsappTestResult) ? 'text-red-400' : 'text-green-400'}`}>
              {whatsappTestResult}
            </p>
          )}
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

      {selectedUser && (
        <ConfirmDialog
          open={showRemoveUserConfirm}
          title={`Remove ${selectedUser.name}`}
          description={`This will permanently delete ${selectedUser.name}'s account, conversation history, facts, and revoke their service accounts (Jellyfin, Audiobookshelf, etc.). This cannot be undone.`}
          confirmLabel={isRemovingUser ? 'Removing...' : `Remove ${selectedUser.name}`}
          onConfirm={() => removeUser(selectedUser.id)}
          onCancel={() => { setShowRemoveUserConfirm(false); setRemoveUserError(null) }}
        />
      )}
    </div>
  )
}
