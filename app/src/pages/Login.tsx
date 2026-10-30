import { useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { api } from '../services/api'
import type { AuthTokens, UserRole } from '../types/user'

interface AuthResponse {
  tokens: AuthTokens
  hasCompletedOnboarding: boolean
  role: UserRole
  username?: string | null
}

/** Sign in with your login; an invite code only creates a new account, and a
 *  reset code (from an admin) lets you choose a new password. */
type Mode = 'signin' | 'invite' | 'reset'

const MIN_PASSWORD_LENGTH = 10

export default function Login() {
  const [mode, setMode] = useState<Mode>('signin')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const { setTokens, setRole, setOnboardingComplete } = useAuthStore()

  function switchMode(next: Mode) {
    setMode(next)
    setError('')
    setCode('')
  }

  function signedIn(response: AuthResponse) {
    setTokens(response.tokens)
    setRole(response.role)
    setOnboardingComplete(response.hasCompletedOnboarding)
  }

  const canSubmit =
    mode === 'signin' ? username.trim().length > 0 && password.length > 0
      : mode === 'invite' ? code.trim().length >= 5
        : code.trim().length >= 8 && newPassword.length >= MIN_PASSWORD_LENGTH && newPassword === confirmPassword

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)
    try {
      if (mode === 'signin') {
        signedIn(await api.post<AuthResponse>('/auth/login', { username: username.trim(), password }))
      } else if (mode === 'invite') {
        signedIn(await api.post<AuthResponse>('/auth/redeem-invite', { code: code.trim().toUpperCase() }))
      } else {
        signedIn(await api.post<AuthResponse>('/auth/reset-password', { code: code.trim(), newPassword }))
      }
    } catch (err) {
      // Dev-only mock code — stripped from production builds by Vite
      if (import.meta.env.DEV && mode === 'invite' && code.toUpperCase() === 'DEV-123') {
        setTokens({
          accessToken: 'mock_access_token',
          refreshToken: 'mock_refresh_token',
          expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000,
        })
        setRole('admin')
        setOnboardingComplete(false)
      } else {
        setError(err instanceof Error ? err.message : 'Something went wrong')
      }
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 bg-butler-900">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-20 h-20 rounded-full bg-gradient-to-br from-accent to-blue-700 flex items-center justify-center mb-4">
            <span className="text-white font-bold text-3xl">B</span>
          </div>
          <h1 className="text-2xl font-bold text-butler-100">Butler</h1>
          <p className="text-butler-400 mt-1">Your AI Home Assistant</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'signin' && (
            <>
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-butler-300 mb-2">Username</label>
                <input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="input"
                  autoCapitalize="none"
                  autoCorrect="off"
                  autoComplete="username"
                  autoFocus
                />
              </div>
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-butler-300 mb-2">Password</label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input"
                  autoComplete="current-password"
                />
                <p className="text-xs text-butler-500 mt-1">The same login you use for Jellyfin.</p>
              </div>
            </>
          )}

          {mode === 'invite' && (
            <div>
              <label htmlFor="invite-code" className="block text-sm font-medium text-butler-300 mb-2">Invite Code</label>
              <input
                id="invite-code"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="Enter code"
                className="input text-center text-xl tracking-widest font-mono"
                maxLength={10}
                autoComplete="off"
                autoFocus
              />
              <p className="text-xs text-butler-500 mt-1">For a new account. You'll choose your login next.</p>
            </div>
          )}

          {mode === 'reset' && (
            <>
              <div>
                <label htmlFor="reset-code" className="block text-sm font-medium text-butler-300 mb-2">Reset Code</label>
                <input
                  id="reset-code"
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="XXXX-XXXX"
                  className="input text-center text-xl tracking-widest font-mono"
                  maxLength={12}
                  autoComplete="one-time-code"
                  autoFocus
                />
                <p className="text-xs text-butler-500 mt-1">Ask an admin for one. It works once, for 24 hours.</p>
              </div>
              <div>
                <label htmlFor="new-password" className="block text-sm font-medium text-butler-300 mb-2">New Password</label>
                <input
                  id="new-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
                  className="input"
                  autoComplete="new-password"
                />
              </div>
              <div>
                <label htmlFor="confirm-password" className="block text-sm font-medium text-butler-300 mb-2">Confirm Password</label>
                <input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="input"
                  autoComplete="new-password"
                />
                {newPassword && confirmPassword && newPassword !== confirmPassword && (
                  <p className="text-xs text-red-400 mt-1">Passwords do not match</p>
                )}
                <p className="text-xs text-butler-500 mt-1">
                  This becomes your password for Butler and all your apps.
                </p>
              </div>
            </>
          )}

          {error && (
            <p className="text-red-400 text-sm text-center" role="alert">{error}</p>
          )}

          <button
            type="submit"
            disabled={!canSubmit || isLoading}
            className="btn btn-primary w-full py-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading
              ? 'Checking...'
              : mode === 'signin' ? 'Sign In' : mode === 'invite' ? 'Create Account' : 'Set Password & Sign In'}
          </button>
        </form>

        <div className="flex flex-col items-center gap-2 mt-8 text-sm">
          {mode !== 'signin' && (
            <button onClick={() => switchMode('signin')} className="text-accent hover:text-accent/80">
              Sign in with your username
            </button>
          )}
          {mode !== 'reset' && (
            <button onClick={() => switchMode('reset')} className="text-butler-400 hover:text-butler-200">
              Forgot your password? Have a reset code?
            </button>
          )}
          {mode !== 'invite' && (
            <button onClick={() => switchMode('invite')} className="text-butler-400 hover:text-butler-200">
              New here? Have an invite code?
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
