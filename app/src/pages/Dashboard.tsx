import { useEffect, useState, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import StatusCard from '../components/dashboard/StatusCard'
import Section from '../components/dashboard/Section'
import ComputePanel from '../components/dashboard/ComputePanel'
import StoragePanel from '../components/dashboard/StoragePanel'
import MediaInbox from '../components/dashboard/MediaInbox'
import { useAuthStore } from '../stores/authStore'
import {
  getSystemHealth,
  getSystemStorage,
  getSystemStats,
  getSystemAlerts,
  getDownloads,
  getStatsHistory,
  type ServiceStatus,
  type StatsHistoryResponse,
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

/** Group services by `stack`, ordered by STACK_ORDER; offline first within a group. */
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
  stats: SystemStatsResponse | null,
): AttentionItem[] {
  const items: AttentionItem[] = []

  for (const svc of health?.services ?? []) {
    if (svc.status !== 'online') {
      items.push({ key: `svc:${svc.name}`, severity: 'critical', title: `${svc.name} is down`, detail: svc.detail })
    }
  }

  for (const a of alerts) {
    if (a.type === 'service_down' && health) continue // duplicates the live probe above
    items.push({
      key: `alert:${a.id}`,
      severity: a.severity === 'critical' ? 'critical' : 'warning',
      title: a.message,
      detail: a.firstTriggeredAt ? `since ${new Date(a.firstTriggeredAt).toLocaleString()}` : undefined,
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

  // Prefer the host agent's drive list (it sees every drive); fall back to volumes.
  const drives = storage?.drives?.filter(d => d.mounted && typeof d.percent === 'number')
  if (drives?.length) {
    for (const d of drives) {
      if ((d.percent ?? 0) >= DISK_WARN_PERCENT) {
        items.push({
          key: `disk:${d.name}`,
          severity: (d.percent ?? 0) >= 90 ? 'critical' : 'warning',
          title: `${d.name} is ${d.percent}% full`,
          detail: `${d.freeFormatted} free of ${d.totalFormatted}`,
        })
      }
    }
  } else {
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
  }

  const host = stats?.host
  if (host?.memory.percent && host.memory.percent >= 92) {
    items.push({
      key: 'host:mem',
      severity: 'warning',
      title: `Mac memory at ${host.memory.percent}%`,
      detail: `${host.memory.usedFormatted} used · swap ${host.swap.percent ?? 0}%`,
    })
  }

  return items.sort((a, b) => Number(b.severity === 'critical') - Number(a.severity === 'critical'))
}

export default function Dashboard() {
  const isAdmin = useAuthStore(s => s.role === 'admin')
  const [health, setHealth] = useState<SystemHealthResponse | null>(null)
  const [storage, setStorage] = useState<SystemStorageResponse | null>(null)
  const [stats, setStats] = useState<SystemStatsResponse | null>(null)
  const [history, setHistory] = useState<StatsHistoryResponse | null>(null)
  const [historyMinutes, setHistoryMinutes] = useState<number>(() => {
    try { return Number(localStorage.getItem('dash-history-minutes')) || 10 } catch { return 10 }
  })
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
      const [h, st, sg, al, dl, hi] = await Promise.allSettled([
        getSystemHealth(),
        getSystemStats(),
        getSystemStorage(),
        getSystemAlerts(),
        getDownloads(),
        getStatsHistory(60),
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
      if (hi.status === 'fulfilled') setHistory(hi.value)
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
    <div className="flex items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold text-butler-100">Dashboard</h1>
        <p className="text-sm text-butler-400">Server status and monitoring</p>
      </div>
      <div className="flex items-center gap-3 text-xs text-butler-500">
        {updatedAt && <span className="tabular-nums">Updated {updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>}
        <button className="btn btn-secondary text-xs py-1.5" onClick={() => fetchAll(false)}>
          Refresh
        </button>
      </div>
    </div>
  )

  if (loadState === 'loading') {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-8">
        {header}
        <LoadingSkeleton />
      </div>
    )
  }

  if (loadState === 'error' && !health) {
    return (
      <div className="flex-1 overflow-y-auto p-4 space-y-8">
        {header}
        <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />
      </div>
    )
  }

  const attention = buildAttention(health, alerts, torrents, storage, stats)

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-8 pb-24 md:pb-8">
      {header}

      {errorMsg && <ErrorBanner message={errorMsg} onRetry={() => fetchAll(true)} />}

      {/* Attention — anything that needs a human, most severe first */}
      <Section title="Attention" aside={attention.length ? `${attention.length} item${attention.length === 1 ? '' : 's'}` : undefined}>
        {attention.length === 0 ? (
          <div className="card p-3 flex items-center gap-2 border-green-500/20">
            <span className="text-green-400" aria-hidden>✓</span>
            <span className="text-sm text-butler-200">All clear — nothing needs you right now.</span>
          </div>
        ) : (
          <div className="space-y-2">
            {attention.map(item => (
              <AttentionRow key={item.key} item={item} />
            ))}
          </div>
        )}
      </Section>

      <ComputePanel
        stats={stats}
        history={history}
        minutes={historyMinutes}
        onMinutes={m => {
          setHistoryMinutes(m)
          try { localStorage.setItem('dash-history-minutes', String(m)) } catch { /* ignore */ }
        }}
      />

      <StoragePanel storage={storage} />

      {isAdmin && <MediaInbox />}

      {/* Services — grouped by stack, offline first */}
      {health && (
        <Section title="Services" aside={`${health.summary.healthy}/${health.summary.total} healthy`}>
          <div className="card p-4 space-y-4">
            {groupByStack(health.services).map(([stack, svcs]) => {
              const up = svcs.filter(s => s.status === 'online').length
              return (
                <div key={stack}>
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="text-xs font-semibold text-butler-300">{STACK_LABELS[stack] ?? stack}</h3>
                    <span className={`text-xs tabular-nums ${up < svcs.length ? 'text-yellow-400' : 'text-butler-500'}`}>
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
        </Section>
      )}
    </div>
  )
}

function AttentionRow({ item }: { item: AttentionItem }) {
  const critical = item.severity === 'critical'
  const body = (
    <div className={`card p-3 ${critical ? 'border-red-500/30 bg-red-500/10' : 'border-yellow-500/30 bg-yellow-500/10'}`}>
      <div className="flex items-start gap-2">
        <span className={critical ? 'text-red-400' : 'text-yellow-400'} aria-hidden>{critical ? '✕' : '!'}</span>
        <div className="min-w-0 flex-1">
          <p className={`text-sm font-medium ${critical ? 'text-red-300' : 'text-yellow-300'}`}>{item.title}</p>
          {item.detail && <p className="text-xs text-butler-400 truncate">{item.detail}</p>}
        </div>
        {item.link && <span className="text-xs text-butler-500" aria-hidden>›</span>}
      </div>
    </div>
  )
  return item.link ? <Link to={item.link} className="block">{body}</Link> : body
}

function LoadingSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="h-12 bg-butler-800 rounded-xl" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {[1, 2].map(i => (
          <div key={i} className="card p-4 space-y-3">
            <div className="h-4 w-24 bg-butler-700 rounded" />
            <div className="h-3 bg-butler-700 rounded" />
            <div className="h-3 bg-butler-700 rounded" />
            <div className="h-3 bg-butler-700 rounded" />
          </div>
        ))}
      </div>
      <div className="card p-4 space-y-3">
        <div className="h-8 w-40 bg-butler-700 rounded" />
        <div className="h-3 bg-butler-700 rounded" />
      </div>
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
