import { useEffect, useState, useCallback } from 'react'
import {
  getDownloads,
  pauseTorrent,
  resumeTorrent,
  deleteTorrent,
  type DownloadsResponse,
  type TorrentInfo,
} from '../services/api'

const REFRESH_INTERVAL = 10_000

type LoadState = 'loading' | 'loaded' | 'error'

const STATE_COLORS: Record<string, string> = {
  downloading: 'bg-green-500/20 text-green-400',
  seeding: 'bg-blue-500/20 text-blue-400',
  paused: 'bg-yellow-500/20 text-yellow-400',
  stalled: 'bg-butler-600 text-butler-300',
  queued: 'bg-butler-600 text-butler-300',
  checking: 'bg-butler-600 text-butler-300',
  error: 'bg-red-500/20 text-red-400',
  moving: 'bg-butler-600 text-butler-300',
}

export default function Downloads() {
  const [data, setData] = useState<DownloadsResponse | null>(null)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [actionInProgress, setActionInProgress] = useState<string | null>(null)

  const fetchAll = useCallback(async (isInitial = false) => {
    if (isInitial) setLoadState('loading')

    try {
      const result = await getDownloads()
      setData(result)
      setLoadState('loaded')
      setErrorMsg('')
    } catch (err) {
      setLoadState('error')
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load downloads')
    }
  }, [])

  useEffect(() => {
    fetchAll(true)
    const id = setInterval(() => fetchAll(false), REFRESH_INTERVAL)
    return () => clearInterval(id)
  }, [fetchAll])

  const handlePause = async (hash: string) => {
    setActionInProgress(hash)
    try {
      await pauseTorrent(hash)
      await fetchAll(false)
    } catch { /* will show on next refresh */ }
    setActionInProgress(null)
  }

  const handleResume = async (hash: string) => {
    setActionInProgress(hash)
    try {
      await resumeTorrent(hash)
      await fetchAll(false)
    } catch { /* will show on next refresh */ }
    setActionInProgress(null)
  }

  const handleDelete = async (hash: string, deleteFiles: boolean) => {
    setActionInProgress(hash)
    setConfirmDelete(null)
    try {
      await deleteTorrent(hash, deleteFiles)
      await fetchAll(false)
    } catch { /* will show on next refresh */ }
    setActionInProgress(null)
  }

  if (loadState === 'loading') {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <Header />
        <LoadingSkeleton />
      </div>
    )
  }

  if (loadState === 'error' && !data) {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <Header />
        <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />
      </div>
    )
  }

  const torrents = data?.torrents ?? []
  const summary = data?.summary

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      <Header />

      {errorMsg && <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />}

      {/* Summary bar */}
      {summary && summary.total > 0 && (
        <div className="card p-3 flex flex-wrap items-center gap-3 text-sm">
          <span className="text-butler-100 font-medium">{summary.total} torrent{summary.total !== 1 ? 's' : ''}</span>
          {summary.downloading > 0 && (
            <span className="text-green-400">{summary.downloading} downloading</span>
          )}
          {summary.seeding > 0 && (
            <span className="text-blue-400">{summary.seeding} seeding</span>
          )}
          {summary.paused > 0 && (
            <span className="text-yellow-400">{summary.paused} paused</span>
          )}
          {summary.dlSpeed > 0 && (
            <span className="text-butler-300 ml-auto">{summary.dlSpeedFormatted}</span>
          )}
        </div>
      )}

      {/* Torrent list */}
      {torrents.length === 0 ? (
        <div className="card p-8 text-center">
          <div className="text-butler-400 text-lg mb-2">No active downloads</div>
          <p className="text-sm text-butler-500">Torrents added via Radarr, Sonarr, LazyLibrarian, or BookTool will appear here.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {torrents.map(torrent => (
            <TorrentCard
              key={torrent.hash}
              torrent={torrent}
              isActioning={actionInProgress === torrent.hash}
              isConfirmingDelete={confirmDelete === torrent.hash}
              onPause={() => handlePause(torrent.hash)}
              onResume={() => handleResume(torrent.hash)}
              onDeleteRequest={() => setConfirmDelete(torrent.hash)}
              onDeleteConfirm={(deleteFiles) => handleDelete(torrent.hash, deleteFiles)}
              onDeleteCancel={() => setConfirmDelete(null)}
            />
          ))}
        </div>
      )}

      {/* Quick actions */}
      <section>
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-secondary text-sm" onClick={() => fetchAll(false)}>
            Refresh Now
          </button>
        </div>
      </section>
    </div>
  )
}

function Header() {
  return (
    <div>
      <h1 className="text-xl font-bold text-butler-100">Downloads</h1>
      <p className="text-sm text-butler-400">Torrent status and management</p>
    </div>
  )
}

function TorrentCard({
  torrent,
  isActioning,
  isConfirmingDelete,
  onPause,
  onResume,
  onDeleteRequest,
  onDeleteConfirm,
  onDeleteCancel,
}: {
  torrent: TorrentInfo
  isActioning: boolean
  isConfirmingDelete: boolean
  onPause: () => void
  onResume: () => void
  onDeleteRequest: () => void
  onDeleteConfirm: (deleteFiles: boolean) => void
  onDeleteCancel: () => void
}) {
  const pct = Math.round(torrent.progress * 100)
  const badgeClass = STATE_COLORS[torrent.state] ?? 'bg-butler-600 text-butler-300'
  const isPaused = torrent.state === 'paused'
  const isActive = torrent.state === 'downloading' || torrent.state === 'seeding'

  return (
    <div className="card p-4 space-y-3">
      {/* Top row: name + state badge */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-butler-100 font-medium text-sm truncate" title={torrent.name}>
            {torrent.name}
          </h3>
          {torrent.category && (
            <span className="text-xs text-butler-500">{torrent.category}</span>
          )}
        </div>
        <span className={`shrink-0 px-2 py-0.5 rounded text-xs font-medium ${badgeClass}`}>
          {torrent.state}
        </span>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="h-2 bg-butler-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-butler-400">
          <span>{torrent.downloadedFormatted} / {torrent.sizeFormatted}</span>
          <span>{pct}%</span>
        </div>
      </div>

      {/* Speed + ETA row */}
      {isActive && (
        <div className="flex gap-4 text-xs text-butler-300">
          {torrent.dlSpeed > 0 && <span>↓ {torrent.dlSpeedFormatted}</span>}
          {torrent.upSpeed > 0 && <span>↑ {torrent.upSpeedFormatted}</span>}
          {torrent.state === 'downloading' && torrent.eta > 0 && (
            <span className="ml-auto">ETA {torrent.etaFormatted}</span>
          )}
        </div>
      )}

      {/* Delete confirmation */}
      {isConfirmingDelete ? (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-butler-300">Delete?</span>
          <button
            className="btn btn-secondary text-xs py-1 px-2"
            onClick={() => onDeleteConfirm(false)}
            disabled={isActioning}
          >
            Remove
          </button>
          <button
            className="bg-red-500/20 text-red-400 hover:bg-red-500/30 text-xs py-1 px-2 rounded transition-colors"
            onClick={() => onDeleteConfirm(true)}
            disabled={isActioning}
          >
            Remove + Files
          </button>
          <button
            className="text-butler-400 hover:text-butler-200 text-xs py-1 px-2"
            onClick={onDeleteCancel}
          >
            Cancel
          </button>
        </div>
      ) : (
        /* Action buttons */
        <div className="flex gap-2">
          {isPaused ? (
            <button
              className="btn btn-secondary text-xs py-1 px-2"
              onClick={onResume}
              disabled={isActioning}
            >
              Resume
            </button>
          ) : torrent.state !== 'seeding' ? (
            <button
              className="btn btn-secondary text-xs py-1 px-2"
              onClick={onPause}
              disabled={isActioning}
            >
              Pause
            </button>
          ) : null}
          <button
            className="text-butler-500 hover:text-red-400 text-xs py-1 px-2 transition-colors"
            onClick={onDeleteRequest}
            disabled={isActioning}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="card p-3 h-10 bg-butler-700 rounded" />
      {[1, 2, 3].map(i => (
        <div key={i} className="card p-4 space-y-3">
          <div className="flex justify-between">
            <div className="h-4 w-48 bg-butler-700 rounded" />
            <div className="h-5 w-20 bg-butler-700 rounded" />
          </div>
          <div className="h-2 bg-butler-700 rounded-full" />
          <div className="flex justify-between">
            <div className="h-3 w-32 bg-butler-700 rounded" />
            <div className="h-3 w-8 bg-butler-700 rounded" />
          </div>
        </div>
      ))}
    </div>
  )
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="card border border-red-500/30 bg-red-500/10 p-4 flex items-center justify-between">
      <div>
        <p className="text-red-400 font-medium">Connection Error</p>
        <p className="text-sm text-red-400/70">{message}</p>
      </div>
      <button className="btn btn-secondary text-sm" onClick={onRetry}>
        Retry
      </button>
    </div>
  )
}
