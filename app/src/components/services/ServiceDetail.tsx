import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Service } from '../../types/services'
import type { ServiceCredential } from '../../types/user'
import { SERVICE_DISPLAY_NAMES } from '../../types/user'

interface ServiceDetailProps {
  service: Service
  credentials: ServiceCredential[]
  onClose: () => void
}

/** Map service config IDs to credential service keys used by the backend */
const CREDENTIAL_KEY_MAP: Record<string, string> = {
  'jellyfin': 'jellyfin',
  'audiobookshelf': 'audiobookshelf',
  'lazylibrarian': 'lazylibrarian',
  'immich': 'immich',
  'nextcloud': 'nextcloud',
}

export default function ServiceDetail({ service, credentials, onClose }: ServiceDetailProps) {
  const navigate = useNavigate()
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  useEffect(() => {
    panelRef.current?.focus()
  }, [])

  const guide = service.guide
  const credKey = CREDENTIAL_KEY_MAP[service.id]
  const cred = credKey ? credentials.find(c => c.service === credKey) : null
  const credDisplay = cred
    ? SERVICE_DISPLAY_NAMES[cred.service] || { label: cred.service, description: '' }
    : null

  const handleOpen = () => {
    window.open(service.url, '_blank', 'noopener,noreferrer')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        className="card w-full sm:max-w-md max-h-[85vh] overflow-y-auto mx-0 sm:mx-4 rounded-t-2xl sm:rounded-2xl p-0"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="sticky top-0 bg-butler-900 border-b border-butler-700 px-5 py-4 flex items-center justify-between rounded-t-2xl">
          <div className="flex items-center gap-3">
            <span className="text-3xl">{service.icon}</span>
            <div>
              <h2 className="text-lg font-semibold text-butler-100">{service.name}</h2>
              <p className="text-xs text-butler-400">{service.description}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {service.status && (
              <div
                className={`w-2 h-2 rounded-full ${
                  service.status === 'online' ? 'bg-green-500' :
                  service.status === 'offline' ? 'bg-red-500' : 'bg-butler-500'
                }`}
              />
            )}
            <button
              onClick={onClose}
              className="text-butler-400 hover:text-butler-200 p-1"
              aria-label="Close"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="p-5 space-y-5">
          {/* URL display */}
          <div className="flex items-center gap-2 p-3 bg-butler-800 rounded-lg">
            <span className="font-mono text-sm text-butler-300 truncate flex-1">{service.url}</span>
            <button
              onClick={() => navigator.clipboard.writeText(service.url)}
              className="shrink-0 p-1.5 rounded-md text-butler-500 hover:text-accent hover:bg-butler-700 transition-colors"
              title="Copy URL"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            </button>
          </div>

          {/* Open button */}
          <button
            onClick={handleOpen}
            className="btn btn-primary w-full py-3 flex items-center justify-center gap-2"
          >
            Open {service.name}
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </button>

          {/* What it does */}
          {guide && (
            <p className="text-sm text-butler-300">{guide.whatItDoes}</p>
          )}

          {/* Getting Started */}
          {guide && guide.steps.length > 0 && (
            <section>
              <h3 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
                Getting Started
              </h3>
              <ol className="space-y-2">
                {guide.steps.map((step, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="shrink-0 w-5 h-5 rounded-full bg-accent/20 text-accent text-xs flex items-center justify-center font-medium">
                      {i + 1}
                    </span>
                    <span className="text-butler-200">{step}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {/* Mobile App — single official app */}
          {guide?.mobileApp && (
            <section>
              <h3 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
                Get the App
              </h3>
              <div className="flex gap-2">
                {guide.mobileApp.ios && (
                  <a
                    href={guide.mobileApp.ios}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-butler-800 text-butler-200 hover:bg-butler-700 text-sm transition-colors"
                  >
                    <AppleIcon className="w-4 h-4" />
                    App Store
                  </a>
                )}
                {guide.mobileApp.android && (
                  <a
                    href={guide.mobileApp.android}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-butler-800 text-butler-200 hover:bg-butler-700 text-sm transition-colors"
                  >
                    <PlayStoreIcon className="w-4 h-4" />
                    Play Store
                  </a>
                )}
              </div>
            </section>
          )}

          {/* Recommended Apps — multiple third-party options */}
          {guide?.recommendedApps && guide.recommendedApps.length > 0 && (
            <section>
              <h3 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
                Recommended Reader Apps
              </h3>
              <div className="space-y-2">
                {guide.recommendedApps.map((app) => (
                  <div key={app.name} className="flex items-center gap-2">
                    <span className="text-sm text-butler-200 min-w-28 shrink-0">{app.name}</span>
                    {app.ios && (
                      <a
                        href={app.ios}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-butler-800 text-butler-300 hover:bg-butler-700 text-xs transition-colors"
                      >
                        <AppleIcon className="w-3.5 h-3.5" />
                        iOS
                      </a>
                    )}
                    {app.android && (
                      <a
                        href={app.android}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-butler-800 text-butler-300 hover:bg-butler-700 text-xs transition-colors"
                      >
                        <PlayStoreIcon className="w-3.5 h-3.5" />
                        Android
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Your Account */}
          {credKey && (
            <section>
              <h3 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
                Your Account
              </h3>
              {cred && cred.status === 'active' ? (
                <div className="p-3 bg-butler-800 rounded-lg space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-butler-400">Username</span>
                    <span className="font-mono text-xs text-butler-200">{cred.username}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-butler-400">Password</span>
                    <button
                      onClick={() => navigate('/settings')}
                      className="text-xs text-accent hover:text-accent/80"
                    >
                      View in Settings
                    </button>
                  </div>
                  {credDisplay && (
                    <div className="text-xs text-green-400/70 mt-1">Account ready</div>
                  )}
                </div>
              ) : cred && cred.status === 'failed' ? (
                <div className="p-3 bg-butler-800 rounded-lg">
                  <div className="text-xs text-red-400">Account setup failed</div>
                  {cred.errorMessage && (
                    <div className="text-xs text-butler-500 mt-1">{cred.errorMessage}</div>
                  )}
                  <button
                    onClick={() => navigate('/settings')}
                    className="text-xs text-accent hover:text-accent/80 mt-2"
                  >
                    Check Settings
                  </button>
                </div>
              ) : (
                <div className="p-3 bg-butler-800 rounded-lg">
                  <div className="text-xs text-butler-500">
                    No account set up yet. Ask an admin for an invite or check Settings.
                  </div>
                  <button
                    onClick={() => navigate('/settings')}
                    className="text-xs text-accent hover:text-accent/80 mt-2"
                  >
                    Go to Settings
                  </button>
                </div>
              )}
            </section>
          )}

          {/* Tips */}
          {guide?.tips && guide.tips.length > 0 && (
            <section>
              <h3 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
                Tips
              </h3>
              <ul className="space-y-2">
                {guide.tips.map((tip, i) => (
                  <li key={i} className="flex gap-2 text-sm text-butler-300">
                    <span className="text-accent shrink-0">*</span>
                    {tip}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

function AppleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
    </svg>
  )
}

function PlayStoreIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M3.609 1.814L13.792 12 3.61 22.186a.996.996 0 01-.61-.92V2.734a1 1 0 01.609-.92zm10.89 10.893l2.302 2.302-10.937 6.333 8.635-8.635zm3.199-3.199l2.302 2.302-2.302 2.302-2.698-2.302 2.698-2.302zM5.864 2.658L16.8 8.99l-2.302 2.302-8.635-8.635z" />
    </svg>
  )
}
