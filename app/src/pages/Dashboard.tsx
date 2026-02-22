import { useEffect, useState, useCallback } from 'react'
import StatusCard from '../components/dashboard/StatusCard'
import {
  getSystemHealth,
  getSystemStorage,
  getSystemStats,
  type SystemHealthResponse,
  type SystemStorageResponse,
  type SystemStatsResponse,
} from '../services/api'

const REFRESH_INTERVAL = 30_000

type LoadState = 'loading' | 'loaded' | 'error'

export default function Dashboard() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null)
  const [storage, setStorage] = useState<SystemStorageResponse | null>(null)
  const [stats, setStats] = useState<SystemStatsResponse | null>(null)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errorMsg, setErrorMsg] = useState('')

  const fetchAll = useCallback(async (isInitial = false) => {
    if (isInitial) setLoadState('loading')

    try {
      const [h, st, sg] = await Promise.all([
        getSystemHealth(),
        getSystemStats(),
        getSystemStorage(),
      ])
      setHealth(h)
      setStats(st)
      setStorage(sg)
      setLoadState('loaded')
      setErrorMsg('')
    } catch (err) {
      setLoadState('error')
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load monitoring data')
    }
  }, [])

  useEffect(() => {
    fetchAll(true)
    const id = setInterval(() => fetchAll(false), REFRESH_INTERVAL)
    return () => clearInterval(id)
  }, [fetchAll])

  if (loadState === 'loading') {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <div>
          <h1 className="text-xl font-bold text-butler-100">Dashboard</h1>
          <p className="text-sm text-butler-400">Server status and monitoring</p>
        </div>
        <LoadingSkeleton />
      </div>
    )
  }

  if (loadState === 'error' && !health) {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <div>
          <h1 className="text-xl font-bold text-butler-100">Dashboard</h1>
          <p className="text-sm text-butler-400">Server status and monitoring</p>
        </div>
        <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      <div>
        <h1 className="text-xl font-bold text-butler-100">Dashboard</h1>
        <p className="text-sm text-butler-400">Server status and monitoring</p>
      </div>

      {errorMsg && <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />}

      {/* Connection Status */}
      {health && (
        <section>
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
            Services ({health.summary.healthy}/{health.summary.total} healthy)
          </h2>
          <div className="flex flex-wrap gap-2">
            {health.services.map(svc => (
              <StatusCard
                key={svc.name}
                name={svc.name}
                status={svc.status === 'online' ? 'online' : 'offline'}
              />
            ))}
          </div>
        </section>
      )}

      {/* System & Storage */}
      <div className="grid grid-cols-2 gap-4">
        <section className="card p-4">
          <h3 className="text-sm font-medium text-butler-400 mb-3">System</h3>
          <div className="space-y-3">
            {stats?.cpu ? (
              <MetricBar label="CPU" percent={stats.cpu.percent} value={`${stats.cpu.percent}%`} />
            ) : (
              <PlaceholderRow label="CPU" />
            )}
            {stats?.memory ? (
              <>
                <MetricBar
                  label="Docker VM"
                  percent={stats.memory.dockerPercent}
                  value={`${stats.memory.dockerUsedFormatted} / ${stats.memory.dockerTotalFormatted}`}
                  hint="RAM used within container runtime"
                />
                {stats.memory.hostTotalGb && (
                  <MetricBar
                    label="Mac Host"
                    percent={Math.round(stats.memory.dockerTotal / (stats.memory.hostTotalGb * 1024 ** 3) * 100)}
                    value={`${stats.memory.dockerTotalFormatted} / ${stats.memory.hostTotalGb} GB`}
                    hint="Docker's allocation of Mac RAM"
                  />
                )}
              </>
            ) : (
              <PlaceholderRow label="RAM" />
            )}
            <div className="flex justify-between text-xs pt-1">
              <span className="text-butler-400">Uptime</span>
              <span className="text-butler-200">{stats?.uptimeFormatted ?? '--'}</span>
            </div>
          </div>
        </section>

        <section className="card p-4">
          <h3 className="text-sm font-medium text-butler-400 mb-3">Storage</h3>
          <div className="space-y-2">
            {storage && storage.volumes.length > 0 ? (
              storage.volumes.map(vol => (
                <div key={vol.name} className="flex justify-between">
                  <span className="text-butler-300">{vol.name}</span>
                  <span className={vol.percent > 80 ? 'text-red-400' : vol.percent > 60 ? 'text-yellow-400' : 'text-green-400'}>
                    {vol.usedFormatted} / {vol.totalFormatted}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-butler-500 text-sm">No volumes detected</div>
            )}
          </div>
        </section>
      </div>

      {/* Storage Categories (if external drive has breakdown) */}
      {storage?.volumes.some(v => v.categories && Object.keys(v.categories).length > 0) && (
        <section>
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
            Storage Breakdown
          </h2>
          <div className="card divide-y divide-butler-700">
            {storage.volumes
              .filter(v => v.categories)
              .map(vol =>
                Object.entries(vol.categories!)
                  .sort(([, a], [, b]) => b.bytes - a.bytes)
                  .map(([label, info]) => (
                    <div key={label} className="p-3 flex justify-between items-center">
                      <span className="text-butler-100 font-medium">{label}</span>
                      <span className="text-sm text-butler-400">{info.formatted}</span>
                    </div>
                  ))
              )}
          </div>
        </section>
      )}

      {/* Quick Actions */}
      <section>
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-secondary text-sm" onClick={() => fetchAll(false)}>
            Refresh Now
          </button>
        </div>
      </section>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex flex-wrap gap-2">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-8 w-24 bg-butler-700 rounded-full" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="card p-4 space-y-3">
          <div className="h-4 w-16 bg-butler-700 rounded" />
          <div className="h-4 bg-butler-700 rounded" />
          <div className="h-4 bg-butler-700 rounded" />
        </div>
        <div className="card p-4 space-y-3">
          <div className="h-4 w-16 bg-butler-700 rounded" />
          <div className="h-4 bg-butler-700 rounded" />
          <div className="h-4 bg-butler-700 rounded" />
        </div>
      </div>
    </div>
  )
}

function MetricBar({
  label,
  percent,
  value,
  hint,
}: {
  label: string
  percent: number
  value: string
  hint?: string
}) {
  const barColor =
    percent > 80 ? 'bg-red-400' : percent > 60 ? 'bg-yellow-400' : 'bg-green-400'

  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-butler-400">{label}</span>
        <span className="text-butler-200">{value}</span>
      </div>
      <div className="w-full bg-butler-700 rounded-full h-1.5">
        <div
          className={`h-1.5 rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      {hint && <p className="text-xs text-butler-500 mt-0.5 text-right">{hint}</p>}
    </div>
  )
}

function PlaceholderRow({ label }: { label: string }) {
  return (
    <div className="flex justify-between text-xs">
      <span className="text-butler-400">{label}</span>
      <span className="text-butler-500">--</span>
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
