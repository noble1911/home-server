import { useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useUserStore } from '../stores/userStore'
import { api } from '../services/api'
import type { SoulConfig } from '../types/user'
import { DEFAULT_VOICE, SERVICE_DISPLAY_NAMES, VOICE_OPTIONS } from '../types/user'

type Step = 'welcome' | 'name' | 'butler-name' | 'personality' | 'voice' | 'credentials' | 'done'

const STEPS: Step[] = ['welcome', 'name', 'butler-name', 'personality', 'voice', 'credentials', 'done']

interface OnboardingData {
  name: string
  butlerName: string
  soul: SoulConfig
  serviceUsername?: string
  servicePassword?: string
}

interface ServiceAccountResult {
  service: string
  username: string
  status: string
  error?: string
}

export default function Onboarding() {
  const [step, setStep] = useState<Step>('welcome')
  const [userName, setUserName] = useState('')
  const [butlerNameInput, setButlerNameInput] = useState('Jarvis')
  const [personality, setPersonality] = useState<SoulConfig['personality']>('balanced')
  const [selectedVoice, setSelectedVoice] = useState(DEFAULT_VOICE)
  const [serviceUsername, setServiceUsername] = useState('')
  const [servicePassword, setServicePassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [provisioningResults, setProvisioningResults] = useState<ServiceAccountResult[] | null>(null)

  const { setOnboardingComplete } = useAuthStore()
  const { fetchProfile } = useUserStore()

  const usernameError = serviceUsername && !/^[a-z0-9_]{3,20}$/.test(serviceUsername)
    ? 'Lowercase letters, numbers, and underscores only (3-20 chars)'
    : null

  const passwordError = servicePassword && servicePassword.length < 6
    ? 'Password must be at least 6 characters'
    : null

  const confirmError = confirmPassword && confirmPassword !== servicePassword
    ? 'Passwords do not match'
    : null

  const credentialsValid =
    serviceUsername.length >= 3 &&
    !usernameError &&
    servicePassword.length >= 6 &&
    servicePassword === confirmPassword

  const handleComplete = async () => {
    setIsSubmitting(true)

    try {
      // Save onboarding data to API
      const data: OnboardingData = {
        name: userName,
        butlerName: butlerNameInput,
        soul: {
          personality,
          verbosity: 'moderate',
          humor: 'subtle',
          voice: selectedVoice,
        },
      }

      // Include service credentials if provided
      if (credentialsValid) {
        data.serviceUsername = serviceUsername
        data.servicePassword = servicePassword
      }

      const response = await api.post<{ status: string; serviceAccounts: ServiceAccountResult[] }>('/user/onboarding', data)

      // Fetch the complete profile
      await fetchProfile()

      // If service accounts were provisioned and some failed, show results
      const accounts = response.serviceAccounts || []
      const hasFailed = accounts.some(a => a.status === 'failed')
      if (hasFailed) {
        setProvisioningResults(accounts)
        setIsSubmitting(false)
        return
      }

      // All good — proceed
      setOnboardingComplete(true)
    } catch {
      // For development: allow mock completion
      setOnboardingComplete(true)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 bg-butler-900">
      <div className="w-full max-w-md">
        {/* Progress Dots */}
        <div className="flex justify-center gap-2 mb-8">
          {STEPS.map((s, i) => (
            <div
              key={s}
              className={`w-2 h-2 rounded-full transition-colors ${
                step === s ? 'bg-accent' : i < STEPS.indexOf(step) ? 'bg-accent/50' : 'bg-butler-700'
              }`}
            />
          ))}
        </div>

        {step === 'welcome' && (
          <div className="text-center">
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-accent to-blue-700 flex items-center justify-center mx-auto mb-6">
              <span className="text-white font-bold text-3xl">B</span>
            </div>
            <h1 className="text-2xl font-bold text-butler-100 mb-2">Welcome to Butler</h1>
            <p className="text-butler-400 mb-8">Let's set up your personal AI assistant.</p>
            <button onClick={() => setStep('name')} className="btn btn-primary w-full py-3">
              Get Started
            </button>
          </div>
        )}

        {step === 'name' && (
          <div>
            <h2 className="text-xl font-bold text-butler-100 mb-2">What's your name?</h2>
            <p className="text-butler-400 mb-6">This helps your butler address you properly.</p>
            <input
              type="text"
              value={userName}
              onChange={(e) => setUserName(e.target.value)}
              placeholder="Enter your name"
              className="input mb-6"
              autoFocus
            />
            <div className="flex gap-3">
              <button onClick={() => setStep('welcome')} className="btn btn-secondary flex-1">
                Back
              </button>
              <button
                onClick={() => setStep('butler-name')}
                disabled={!userName.trim()}
                className="btn btn-primary flex-1 disabled:opacity-50"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 'butler-name' && (
          <div>
            <h2 className="text-xl font-bold text-butler-100 mb-2">Name your butler</h2>
            <p className="text-butler-400 mb-6">What should your AI assistant call itself?</p>
            <input
              type="text"
              value={butlerNameInput}
              onChange={(e) => setButlerNameInput(e.target.value)}
              placeholder="e.g., Jarvis, Friday, Alfred"
              className="input mb-4"
              autoFocus
            />
            <div className="flex flex-wrap gap-2 mb-6">
              {['Jarvis', 'Friday', 'Alfred', 'Samantha', 'Max'].map((name) => (
                <button
                  key={name}
                  onClick={() => setButlerNameInput(name)}
                  className={`px-3 py-1 rounded-full text-sm transition-colors ${
                    butlerNameInput === name
                      ? 'bg-accent text-white'
                      : 'bg-butler-800 text-butler-300 hover:bg-butler-700'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <button onClick={() => setStep('name')} className="btn btn-secondary flex-1">
                Back
              </button>
              <button
                onClick={() => setStep('personality')}
                disabled={!butlerNameInput.trim()}
                className="btn btn-primary flex-1 disabled:opacity-50"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 'personality' && (
          <div>
            <h2 className="text-xl font-bold text-butler-100 mb-2">Choose a personality</h2>
            <p className="text-butler-400 mb-6">How should {butlerNameInput} communicate?</p>
            <div className="space-y-3 mb-6">
              {[
                { value: 'casual' as const, label: 'Casual', desc: 'Friendly and relaxed' },
                { value: 'balanced' as const, label: 'Balanced', desc: 'Professional yet approachable' },
                { value: 'formal' as const, label: 'Formal', desc: 'Professional and precise' },
              ].map((option) => (
                <button
                  key={option.value}
                  onClick={() => setPersonality(option.value)}
                  className={`w-full p-4 rounded-lg border text-left transition-colors ${
                    personality === option.value
                      ? 'border-accent bg-accent/10'
                      : 'border-butler-700 bg-butler-800 hover:border-butler-600'
                  }`}
                >
                  <div className="font-medium text-butler-100">{option.label}</div>
                  <div className="text-sm text-butler-400">{option.desc}</div>
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <button onClick={() => setStep('butler-name')} className="btn btn-secondary flex-1">
                Back
              </button>
              <button onClick={() => setStep('voice')} className="btn btn-primary flex-1">
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 'voice' && (
          <div>
            <h2 className="text-xl font-bold text-butler-100 mb-2">Choose a voice</h2>
            <p className="text-butler-400 mb-6">How should {butlerNameInput} sound during voice conversations?</p>
            <div className="space-y-3 mb-6">
              {VOICE_OPTIONS.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setSelectedVoice(v.id)}
                  className={`w-full p-4 rounded-lg border text-left transition-colors ${
                    selectedVoice === v.id
                      ? 'border-accent bg-accent/10'
                      : 'border-butler-700 bg-butler-800 hover:border-butler-600'
                  }`}
                >
                  <div className="font-medium text-butler-100">{v.name}</div>
                  <div className="text-sm text-butler-400">{v.accent} {v.gender}</div>
                </button>
              ))}
            </div>
            <div className="flex gap-3">
              <button onClick={() => setStep('personality')} className="btn btn-secondary flex-1">
                Back
              </button>
              <button onClick={() => setStep('credentials')} className="btn btn-primary flex-1">
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 'credentials' && (
          <div>
            <h2 className="text-xl font-bold text-butler-100 mb-2">Create your app login</h2>
            <p className="text-butler-400 mb-6">
              This login will work across Jellyfin, Nextcloud, Immich, and other apps on your server.
            </p>

            <div className="space-y-4 mb-6">
              <div>
                <label htmlFor="service-username" className="block text-sm text-butler-300 mb-1">
                  Username
                </label>
                <input
                  id="service-username"
                  type="text"
                  value={serviceUsername}
                  onChange={(e) => setServiceUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                  placeholder="e.g., ron"
                  className="input"
                  autoFocus
                  autoComplete="off"
                />
                {usernameError && (
                  <p className="text-xs text-red-400 mt-1">{usernameError}</p>
                )}
              </div>

              <div>
                <label htmlFor="service-password" className="block text-sm text-butler-300 mb-1">
                  Password
                </label>
                <input
                  id="service-password"
                  type="password"
                  value={servicePassword}
                  onChange={(e) => setServicePassword(e.target.value)}
                  placeholder="At least 6 characters"
                  className="input"
                  autoComplete="new-password"
                />
                {passwordError && (
                  <p className="text-xs text-red-400 mt-1">{passwordError}</p>
                )}
              </div>

              <div>
                <label htmlFor="confirm-password" className="block text-sm text-butler-300 mb-1">
                  Confirm Password
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter your password"
                  className="input"
                  autoComplete="new-password"
                />
                {confirmError && (
                  <p className="text-xs text-red-400 mt-1">{confirmError}</p>
                )}
              </div>
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep('voice')} className="btn btn-secondary flex-1">
                Back
              </button>
              <button
                onClick={() => setStep('done')}
                disabled={!credentialsValid}
                className="btn btn-primary flex-1 disabled:opacity-50"
              >
                Continue
              </button>
            </div>

            <button
              onClick={() => setStep('done')}
              className="w-full mt-3 text-sm text-butler-500 hover:text-butler-300 transition-colors"
            >
              Skip for now
            </button>
          </div>
        )}

        {step === 'done' && !provisioningResults && (
          <div className="text-center">
            <div className="w-20 h-20 rounded-full bg-gradient-to-br from-green-500 to-green-700 flex items-center justify-center mx-auto mb-6">
              <svg className="w-10 h-10 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-butler-100 mb-2">You're all set!</h2>
            <p className="text-butler-400 mb-8">
              {butlerNameInput} is ready to help you, {userName}.
            </p>
            <button
              onClick={handleComplete}
              disabled={isSubmitting}
              className="btn btn-primary w-full py-3 disabled:opacity-50"
            >
              {isSubmitting ? 'Creating your accounts...' : 'Start Using Butler'}
            </button>
          </div>
        )}

        {step === 'done' && provisioningResults && (
          <div>
            <h2 className="text-xl font-bold text-butler-100 mb-2">Account Setup Results</h2>
            <p className="text-butler-400 mb-4">
              Some service accounts couldn't be created. You can retry from Settings later.
            </p>
            <div className="space-y-2 mb-6">
              {provisioningResults.map(result => {
                const info = SERVICE_DISPLAY_NAMES[result.service] || { label: result.service, description: '' }
                const ok = result.status === 'active'
                return (
                  <div key={result.service} className="flex items-center justify-between p-3 bg-butler-800 rounded-lg">
                    <div>
                      <div className="text-sm text-butler-100">{info.label}</div>
                      <div className="text-xs text-butler-500">{info.description}</div>
                    </div>
                    {ok ? (
                      <span className="text-xs text-green-400">Created</span>
                    ) : (
                      <span className="text-xs text-red-400">Failed</span>
                    )}
                  </div>
                )
              })}
            </div>
            <button
              onClick={() => setOnboardingComplete(true)}
              className="btn btn-primary w-full py-3"
            >
              Continue to Butler
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
