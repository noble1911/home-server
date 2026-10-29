import { useEffect, useState } from 'react'
import { getIptvProvider, setIptvProvider, syncIptvProvider, type IptvProviderSettings } from '../../services/api'

type Kind = 'xtream' | 'm3u'

/** Admin-only: the household's IPTV provider login, pushed into Dispatcharr for Jellyfin's Live TV. */
export default function IptvProviderSetting() {
  const [state, setState] = useState<IptvProviderSettings | null>(null)
  const [kind, setKind] = useState<Kind>('xtream')
  const [serverUrl, setServerUrl] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [m3uUrl, setM3uUrl] = useState('')
  const [maxStreams, setMaxStreams] = useState(1)
  const [dispatcharrUsername, setDispatcharrUsername] = useState('')
  const [dispatcharrPassword, setDispatcharrPassword] = useState('')
  const [busy, setBusy] = useState<'save' | 'sync' | null>(null)
  const [error, setError] = useState<string | null>(null)

  function load(s: IptvProviderSettings) {
    setState(s)
    if (s.kind) setKind(s.kind)
    setServerUrl(s.serverUrl ?? '')
    setUsername(s.username ?? '')
    setMaxStreams(s.maxStreams)
    setDispatcharrUsername(s.dispatcharrUsername ?? '')
    setPassword('')
    setM3uUrl('')
    setDispatcharrPassword('')
  }

  useEffect(() => {
    getIptvProvider().then(load).catch(err => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [])

  async function run(action: 'save' | 'sync') {
    setBusy(action)
    setError(null)
    try {
      load(action === 'save'
        ? await setIptvProvider({ kind, serverUrl, username, password, m3uUrl, maxStreams, dispatcharrUsername, dispatcharrPassword })
        : await syncIptvProvider())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setBusy(null)
    }
  }

  // A saved secret can be kept by leaving its field blank
  const keepsPassword = state?.kind === 'xtream' && state.hasPassword
  const keepsM3u = state?.kind === 'm3u' && state.hasM3uUrl
  const keepsDispatcharrPassword = !!state?.hasDispatcharrPassword && dispatcharrUsername.trim() === state.dispatcharrUsername
  const dispatcharrLoginOk = !dispatcharrUsername.trim() || !!dispatcharrPassword || keepsDispatcharrPassword
  const canSave = dispatcharrLoginOk && (kind === 'xtream'
    ? !!serverUrl.trim() && !!username.trim() && (!!password || keepsPassword)
    : !!m3uUrl.trim() || keepsM3u)

  return (
    <section className="card p-4">
      <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-1">
        Live TV provider
        <span className="text-butler-600 ml-2 text-xs normal-case">admin · everyone</span>
      </h2>
      <p className="text-xs text-butler-500 mb-3">
        Your IPTV login. Butler sends it to Dispatcharr, which feeds the channels to Jellyfin's Live TV.
      </p>

      {!state && !error && <p className="text-sm text-butler-500">Loading…</p>}

      {state && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Provider type">
            {([['xtream', 'Xtream Codes'], ['m3u', 'M3U playlist URL']] as const).map(([id, label]) => (
              <button
                key={id}
                role="radio"
                aria-checked={kind === id}
                onClick={() => setKind(id)}
                className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
                  kind === id ? 'border-accent bg-accent/10 text-butler-100' : 'border-butler-700 text-butler-300 hover:border-butler-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {kind === 'xtream' ? (
            <>
              <input
                type="url"
                value={serverUrl}
                onChange={e => setServerUrl(e.target.value)}
                placeholder="Server URL (e.g. http://provider.example:8080)"
                className="input w-full text-sm"
                autoComplete="off"
              />
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Username"
                className="input w-full text-sm"
                autoComplete="off"
              />
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder={keepsPassword ? 'Password (saved — leave blank to keep)' : 'Password'}
                className="input w-full text-sm"
                autoComplete="new-password"
              />
            </>
          ) : (
            <input
              type="password"
              value={m3uUrl}
              onChange={e => setM3uUrl(e.target.value)}
              placeholder={keepsM3u ? 'Playlist URL (saved — leave blank to keep)' : 'Playlist URL (http://…/get.php?…)'}
              className="input w-full text-sm"
              autoComplete="off"
            />
          )}

          <label className="flex items-center justify-between gap-2 text-sm text-butler-300">
            Simultaneous streams your plan allows
            <input
              type="number"
              min={1}
              max={50}
              value={maxStreams}
              onChange={e => setMaxStreams(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
              className="input w-20 text-sm"
            />
          </label>

          <div className="pt-2">
            <label className="block text-sm text-butler-300 mb-1">Dispatcharr sign-in</label>
            <p className="text-xs text-butler-500 mb-2">
              The Dispatcharr admin Butler signs in as. Leave blank to use your service login.
            </p>
            <div className="space-y-2">
              <input
                type="text"
                value={dispatcharrUsername}
                onChange={e => setDispatcharrUsername(e.target.value)}
                placeholder="Dispatcharr username (case-sensitive)"
                className="input w-full text-sm"
                autoComplete="off"
              />
              {dispatcharrUsername.trim() && (
                <input
                  type="password"
                  value={dispatcharrPassword}
                  onChange={e => setDispatcharrPassword(e.target.value)}
                  placeholder={keepsDispatcharrPassword ? 'Dispatcharr password (saved — leave blank to keep)' : 'Dispatcharr password'}
                  className="input w-full text-sm"
                  autoComplete="new-password"
                />
              )}
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => run('save')}
              disabled={busy !== null || !canSave}
              className="flex-1 btn bg-butler-700 text-butler-300 hover:bg-butler-600 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {busy === 'save' ? 'Saving…' : 'Save & send to Dispatcharr'}
            </button>
            {state.configured && (
              <button
                onClick={() => run('sync')}
                disabled={busy !== null}
                className="btn btn-secondary text-sm disabled:opacity-50"
              >
                {busy === 'sync' ? 'Syncing…' : 'Sync again'}
              </button>
            )}
          </div>

          {state.lastError ? (
            <p className="text-xs text-red-400" role="alert">Not synced: {state.lastError}</p>
          ) : state.lastSyncedAt ? (
            <p className="text-xs text-green-400">
              Synced to Dispatcharr {new Date(state.lastSyncedAt).toLocaleString()}
            </p>
          ) : null}
        </div>
      )}

      {error && <p className="text-xs text-red-400 mt-2" role="alert">{error}</p>}
    </section>
  )
}
