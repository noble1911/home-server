import { useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { api } from '../services/api'
import type { AuthTokens } from '../types/user'

interface RedeemInviteResponse {
  tokens: AuthTokens
  hasCompletedOnboarding: boolean
}

export default function Login() {
  const [inviteCode, setInviteCode] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const { setTokens, setOnboardingComplete } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      // Call API to redeem invite code
      const response = await api.post<RedeemInviteResponse>('/auth/redeem-invite', {
        code: inviteCode.toUpperCase()
      })

      setTokens(response.tokens)
      setOnboardingComplete(response.hasCompletedOnboarding)
    } catch (err) {
      // For development: allow mock code
      if (inviteCode.toUpperCase() === 'DEV-123') {
        setTokens({
          accessToken: 'mock_access_token',
          refreshToken: 'mock_refresh_token',
          expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000,
        })
        setOnboardingComplete(false) // Go to onboarding
      } else {
        setError(
          err instanceof Error
            ? err.message
            : 'Invalid invite code. Try DEV-123 for testing.'
        )
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

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="invite-code" className="block text-sm font-medium text-butler-300 mb-2">
              Invite Code
            </label>
            <input
              id="invite-code"
              type="text"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
              placeholder="XXX-XXX"
              className="input text-center text-xl tracking-widest font-mono"
              maxLength={7}
              autoComplete="off"
              autoFocus
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={inviteCode.length < 5 || isLoading}
            className="btn btn-primary w-full py-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Verifying...' : 'Enter'}
          </button>
        </form>

        <p className="text-butler-500 text-xs text-center mt-8">
          Ask your admin for an invite code to get started.
        </p>
      </div>
    </div>
  )
}
