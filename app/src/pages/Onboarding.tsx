import { useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useUserStore } from '../stores/userStore'
import { api } from '../services/api'
import type { SoulConfig } from '../types/user'

type Step = 'welcome' | 'name' | 'butler-name' | 'personality' | 'done'

interface OnboardingData {
  name: string
  butlerName: string
  soul: SoulConfig
}

export default function Onboarding() {
  const [step, setStep] = useState<Step>('welcome')
  const [userName, setUserName] = useState('')
  const [butlerNameInput, setButlerNameInput] = useState('Jarvis')
  const [personality, setPersonality] = useState<SoulConfig['personality']>('balanced')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const { setOnboardingComplete } = useAuthStore()
  const { fetchProfile } = useUserStore()

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
        },
      }

      await api.post('/user/onboarding', data)

      // Fetch the complete profile
      await fetchProfile()

      // Mark onboarding complete
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
          {(['welcome', 'name', 'butler-name', 'personality', 'done'] as Step[]).map((s, i) => (
            <div
              key={s}
              className={`w-2 h-2 rounded-full transition-colors ${
                step === s ? 'bg-accent' : i < ['welcome', 'name', 'butler-name', 'personality', 'done'].indexOf(step) ? 'bg-accent/50' : 'bg-butler-700'
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
              <button onClick={() => setStep('done')} className="btn btn-primary flex-1">
                Continue
              </button>
            </div>
          </div>
        )}

        {step === 'done' && (
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
              {isSubmitting ? 'Setting up...' : 'Start Using Butler'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
