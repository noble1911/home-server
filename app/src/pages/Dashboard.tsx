import { useEffect, useState, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import StatusCard from '../components/dashboard/StatusCard'
import {
  getSystemHealth,
  getSystemStorage,
  getSystemStats,
  getSystemAlerts,
  getDownloads,
  type ServiceStatus,
  type SystemHealthResponse,
  type SystemStorageResponse,
  type SystemStatsResponse,
  type AlertInfo,
  type TorrentInfo,
} from '../services/api'

const REFRESH_INTERVAL = 30_000
const DISK_WARN_PERCENT = 80

// Human-readable labels + preferred display order for the stacks the
// health endpoint reports (the `stack` field on each service).
const STACK_LABELS: Record<string, string> = {
  butler: 'Butler',
  media: 'Media',
  download: 'Downloads',
  books: 'Books',
  'photos-files': 'Photos & Files',
  'smart-home': 'Smart Home',
  voice: 'Voice',
  messaging: 'Messaging',
  'claude-esp': 'ESP Device',
  apps: 'Apps',
}
const STACK_ORDER = Object.keys(STACK_LABELS)

/** Group services by their `stack`, ordered by STACK_ORDER (unknown stacks last).
 *  Within a group, offline services come first so problems are visible. */
function groupByStack(services: ServiceStatus[]): [string, ServiceStatus[]][] {
  const groups = new Map<string, ServiceStatus[]>()
  for (const svc of services) {
    const key = svc.stack || 'other'
    const arr = groups.get(key) ?? []
    arr.push(svc)
    groups.set(key, arr)
  }
  for (const arr of groups.values()) {
    arr.sort((a, b) => Number(a.status === 'online') - Number(b.status === 'online'))
  }
  return [...groups.entries()].sort(([a], [b]) => {
    const ia = STACK_ORDER.indexOf(a)
    const ib = STACK_ORDER.indexOf(b)
    if (ia !== -1 && ib !== -1) return ia - ib
    if (ia !== -1) return -1
    if (ib !== -1) return 1
    return a.localeCompare(b)
  })
}

type LoadState = 'loading' | 'loaded' | 'error'

interface AttentionItem {
  key: string
  severity: 'critical' | 'warning'
  title: string
  detail?: string
  link?: string
}

/** Everything a home user should look at first, most severe first. */
function buildAttention(
  health: SystemHealthResponse | null,
  alerts: AlertInfo[],
  torrents: TorrentInfo[],
  storage: SystemStorageResponse | null,
): AttentionItem[] {
  const items: AttentionItem[] = []

  for (const svc of health?.services ?? []) {
    if (svc.status !== 'online') {
      items.push({
        key: `svc:${svc.name}`,
        severity: 'critical',
        title: `${svc.name} is down`,
        detail: svc.detail,
      })
    }
  }

  for (const a of alerts) {
    // Service-down alerts duplicate the live probe above; keep the rest.
    if (a.type === 'service_down' && health) continue
    items.push({
      key: `alert:${a.id}`,
      severity: a.severity === 'critical' ? 'critical' : 'warning',
      title: a.message,
      detail: a.lastTriggeredAt ? `since ${new Date(a.firstTriggeredAt ?? a.lastTriggeredAt).toLocaleString()}` : undefined,
    })
  }

  const errored = torrents.filter(t => t.state === 'error')
  const stalled = torrents.filter(t => t.state === 'stalled')
  if (errored.length) {
    items.push({
      key: 'dl:error',
      severity: 'critical',
      title: `${errored.length} download${errored.length > 1 ? 's' : ''} errored`,
      detail: errored.slice(0, 3).map(t => t.name).join(' · '),
      link: '/downloads',
    })
  }
  if (stalled.length) {
    items.push({
      key: 'dl:stalled',
      severity: 'warning',
      title: `${stalled.length} download${stalled.length > 1 ? 's' : ''} stalled`,
      detail: stalled.slice(0, 3).map(t => t.name).join(' · '),
      link: '/downloads',
    })
  }

  for (const vol of storage?.volumes ?? []) {
    if (vol.percent >= DISK_WARN_PERCENT) {
      items.push({
        key: `disk:${vol.name}`,
        severity: vol.percent >= 90 ? 'critical' : 'warning',
        title: `${vol.name} is ${vol.percent}% full`,
        detail: `${vol.freeFormatted} free of ${vol.totalFormatted}`,
      })
    }
  }

  return items.sort((a, b) => Number(b.severity === 'critical') - Number(a.severity === 'critical'))
}

export default function Dashboard() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null)
  const [storage, setStorage] = useState<SystemStorageResponse | null>(null)
  const [stats, setStats] = useState<SystemStatsResponse | null>(null)
  const [alerts, setAlerts] = useState<AlertInfo[]>([])
  const [torrents, setTorrents] = useState<TorrentInfo[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const inFlight = useRef(false)

  const fetchAll = useCallback(async (isInitial = false) => {
    if (inFlight.current) return
    inFlight.current = true
    if (isInitial) setLoadState('loading')

    try {
      // Each source is independent: qBittorrent being down must not blank
      // the whole dashboard. Health is the one we treat as required.
      const [h, st, sg, al, dl] = await Promise.allSettled([
        getSystemHealth(),
        getSystemStats(),
        getSystemStorage(),
        getSystemAlerts(),
        getDownloads(),
      ])

      if (h.status === 'fulfilled') {
        setHealth(h.value)
        setLoadState('loaded')
        setErrorMsg('')
      } else {
        setLoadState('error')
        setErrorMsg(h.reason instanceof Error ? h.reason.message : 'Failed to load monitoring data')
      }
      if (st.status === 'fulfilled') setStats(st.value)
      if (sg.status === 'fulfilled') setStorage(sg.value)
      if (al.status === 'fulfilled') setAlerts(al.value.alerts)
      if (dl.status === 'fulfilled') setTorrents(dl.value.torrents)
      setUpdatedAt(new Date())
    } finally {
      inFlight.current = false
    }
  }, [])

  useEffect(() => {
    fetchAll(true)
    // Poll only while the tab is visible; refresh immediately on return.
    const id = setInterval(() => {
      if (!document.hidden) fetchAll(false)
    }, REFRESH_INTERVAL)
    const onVisible = () => {
      if (!document.hidden) fetchAll(false)
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [fetchAll])

  const header = (
    <div>
      <h1 className="text-xl font-bold text-butler-100">Dashboard</h1>
      <p className="text-sm text-butler-400">Server status and monitoring</p>
    </div>
  )

  if (loadState === 'loading') {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {header}
        <LoadingSkeleton />
      </div>
    )
  }

  if (loadState === 'error' && !health) {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {header}
        <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />
      </div>
    )
  }

  const attention = buildAttention(health, alerts, torrents, storage)

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      {header}

      {errorMsg && <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />}

      {/* Attention — anything that needs a human, most severe first */}
      <section>
        <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
          Attention
        </h2>
        {attention.length === 0 ? (
          <div className="card p-3 flex items-center gap-2 border border-green-500/20">
            <span className="text-green-400">✓</span>
            <span className="text-sm text-butler-200">All clear — nothing needs you right now.</span>
          </div>
        ) : (
          <div className="space-y-2">
            {attention.map(item => (
              <AttentionRow key={item.key} item={item} />
            ))}
          </div>
        )}
      </section>

      {/* Connection Status — grouped by stack, offline first */}
      {health && (
        <section>
          <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-3">
            Services ({health.summary.healthy}/{health.summary.total} healthy)
          </h2>
          <div className="space-y-4">
            {groupByStack(health.services).map(([stack, svcs]) => {
              const up = svcs.filter(s => s.status === 'online').length
              return (
                <div key={stack}>
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-xs font-semibold text-butler-300">
                      {STACK_LABELS[stack] ?? stack}
                    </h3>
                    <span className={`text-xs ${up < svcs.length ? 'text-yellow-400' : 'text-butler-500'}`}>
                      {up}/{svcs.length}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {svcs.map(svc => (
                      <StatusCard
                        key={svc.name}
                        name={svc.name}
                        status={svc.status === 'online' ? 'online' : 'offline'}
                        detail={svc.detail}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* System & Storage */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <section className="card p-4">
          <h3 className="text-sm font-medium text-butler-400 mb-1">Docker VM</h3>
          <p className="text-xs text-butler-500 mb-3">
            The Linux VM running the containers. Native apps (Jellyfin, Ollama) aren't included.
          </p>
          <div className="space-y-3">
            {stats?.cpu ? (
              <MetricBar label="CPU" percent={stats.cpu.percent} value={`${stats.cpu.percent}%`} />
            ) : (
              <PlaceholderRow label="CPU" />
            )}
            {stats?.memory ? (
              <MetricBar
                label="RAM"
                percent={stats.memory.dockerPercent}
                value={`${stats.memory.dockerUsedFormatted} / ${stats.memory.dockerTotalFormatted}`}
                hint={stats.memory.hostTotalGb ? `of the Mac's ${stats.memory.hostTotalGb} GB` : undefined}
              />
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
          <div className="space-y-3">
            {storage && storage.volumes.length > 0 ? (
              storage.volumes.map(vol => (
                <MetricBar
                  key={vol.name}
                  label={vol.name}
                  percent={vol.percent}
                  value={`${vol.usedFormatted} / ${vol.totalFormatted}`}
                  hint={`${vol.freeFormatted} free`}
                />
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
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn btn-secondary text-sm" onClick={() => fetchAll(false)}>
            Refresh Now
          </button>
          {updatedAt && (
            <span className="text-xs text-butler-500">
              Updated {updatedAt.toLocaleTimeString()}
            </span>
          )}
        </div>
      </section>
    </div>
  )
}

function AttentionRow({ item }: { item: AttentionItem }) {
  const critical = item.severity === 'critical'
  const body = (
    <div
      className={`card p-3 border ${
        critical ? 'border-red-500/30 bg-red-500/10' : 'border-yellow-500/30 bg-yellow-500/10'
      }`}
    >
      <div className="flex items-start gap-2">
        <span className={critical ? 'text-red-400' : 'text-yellow-400'}>{critical ? '✕' : '!'}</span>
        <div className="min-w-0 flex-1">
          <p className={`text-sm font-medium ${critical ? 'text-red-300' : 'text-yellow-300'}`}>{item.title}</p>
          {item.detail && <p className="text-xs text-butler-400 truncate">{item.detail}</p>}
        </div>
        {item.link && <span className="text-xs text-butler-500">›</span>}
      </div>
    </div>
  )
  return item.link ? <Link to={item.link} className="block">{body}</Link> : body
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-12 bg-butler-700 rounded-lg" />
      <div className="flex flex-wrap gap-2">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-8 w-24 bg-butler-700 rounded-full" />
        ))}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
