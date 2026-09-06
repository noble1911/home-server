import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getMediaInbox,
  importInboxItems,
  moveInboxItem,
  getInboxJobs,
  refreshJellyfinLibrary,
  type InboxItem,
  type InboxResponse,
  type ArrCommandStatus,
  type MoveJob,
} from '../../services/api'
import { formatAge, formatBytes } from '../../utils/format'
import Section from './Section'

const JOB_POLL_MS = 5_000

/**
 * Media inbox — what's sitting in Downloads/Complete and how to file it.
 *
 * Three kinds of item:
 *  - new:        Sonarr/Radarr recognise it and the library lacks it → Import
 *                (they rename, move to the library drive, update their DB)
 *  - duplicate:  recognised, but the library already has every episode/movie
 *                (a stale seeding copy) → Trash; "Import anyway" replaces
 *  - leftover:   empty, or only nfo/txt/screens left after an import → Trash
 * Anything unrecognised gets a destination picker and a plain host-side move.
 * Trash is Downloads/Trash on the same drive; nothing is deleted for you.
 */
export default function MediaInbox() {
  const [data, setData] = useState<InboxResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<Set<string>>(new Set())
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [dest, setDest] = useState<Record<string, string>>({})
  const [commands, setCommands] = useState<ArrCommandStatus[]>([])
  const [moves, setMoves] = useState<MoveJob[]>([])
  const pollRef = useRef<number | null>(null)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const d = await getMediaInbox()
      setData(d)
      setError(d.error ?? '')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to read inbox')
    } finally {
      setLoading(false)
    }
  }, [])

  const pollJobs = useCallback(async () => {
    try {
      const j = await getInboxJobs()
      setCommands(j.commands)
      setMoves(j.moves)
      const active =
        j.commands.some(c => ['queued', 'started', 'unknown'].includes(c.status)) ||
        j.moves.some(m => m.status === 'queued' || m.status === 'running')
      if (!active && pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
        load() // things moved — rescan
      }
    } catch {
      /* transient */
    }
  }, [load])

  const startPolling = useCallback(() => {
    if (pollRef.current) return
    pollJobs()
    pollRef.current = window.setInterval(pollJobs, JOB_POLL_MS)
  }, [pollJobs])

  useEffect(() => {
    load()
    pollJobs()
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [load, pollJobs])

  const withBusy = async (names: string[], fn: () => Promise<void>) => {
    setBusy(prev => new Set([...prev, ...names]))
    try {
      await fn()
    } finally {
      setBusy(prev => {
        const n = new Set(prev)
        names.forEach(x => n.delete(x))
        return n
      })
    }
  }

  const doImport = (names: string[]) =>
    withBusy(names, async () => {
      const { results } = await importInboxItems(names)
      const n: Record<string, string> = {}
      for (const r of results) {
        n[r.name] =
          r.status === 'queued'
            ? `${r.app === 'sonarr' ? 'Sonarr' : 'Radarr'} is ${r.mode === 'copy' ? 'copying' : 'moving'} ${r.files} file${r.files === 1 ? '' : 's'}…`
            : r.error ?? r.status
      }
      setNotes(prev => ({ ...prev, ...n }))
      startPolling()
    })

  const doMove = (name: string, key: string) =>
    withBusy([name], async () => {
      try {
        await moveInboxItem(name, key)
        setNotes(prev => ({ ...prev, [name]: key === 'trash' ? 'Moving to Trash…' : 'Moving on the host…' }))
        startPolling()
      } catch (e) {
        setNotes(prev => ({ ...prev, [name]: e instanceof Error ? e.message : 'Move failed' }))
      }
    })

  const doTrashMany = (names: string[]) =>
    withBusy(names, async () => {
      for (const name of names) {
        try {
          await moveInboxItem(name, 'trash')
          setNotes(prev => ({ ...prev, [name]: 'Moving to Trash…' }))
        } catch (e) {
          setNotes(prev => ({ ...prev, [name]: e instanceof Error ? e.message : 'Move failed' }))
        }
      }
      startPolling()
    })

  const items = data?.items ?? []
  const kind = (i: InboxItem) => classify(i)
  const newItems = items.filter(i => kind(i) === 'new' && !busy.has(i.name))
  const disposable = items.filter(i => ['duplicate', 'leftover'].includes(kind(i)) && !i.seeding && !busy.has(i.name))
  const activeMoves = moves.filter(m => m.status === 'queued' || m.status === 'running')
  const activeCommands = commands.filter(c => ['queued', 'started'].includes(c.status))
  const sm = data?.summary

  return (
    <Section
      title="Media inbox"
      aside={sm ? `${sm.count} item${sm.count === 1 ? '' : 's'} · ${formatBytes(sm.bytes)}` : undefined}
    >
      <div className="card divide-y divide-butler-700/60">
        <div className="p-3 flex flex-wrap items-center gap-2">
          <p className="text-xs text-butler-400 flex-1 min-w-[14rem]">
            Finished downloads in <span className="text-butler-200">Downloads/Complete</span>.
            {sm && (
              <>
                {' '}<span className="text-butler-200">{sm.importable}</span> new,{' '}
                <span className="text-butler-200">{sm.inLibrary}</span> already in the library,{' '}
                <span className="text-butler-200">{sm.leftovers}</span> leftover.
              </>
            )}
          </p>
          <button className="btn btn-primary text-xs py-1.5" disabled={newItems.length === 0} onClick={() => doImport(newItems.map(i => i.name))}>
            Import new ({newItems.length})
          </button>
          <button className="btn btn-secondary text-xs py-1.5" disabled={disposable.length === 0} onClick={() => doTrashMany(disposable.map(i => i.name))} title="Moves duplicates and leftover folders to Downloads/Trash">
            Trash duplicates ({disposable.length})
          </button>
          <button className="btn btn-ghost text-xs py-1.5" onClick={load} disabled={loading}>
            {loading ? 'Scanning…' : 'Rescan'}
          </button>
          <button className="btn btn-ghost text-xs py-1.5" onClick={() => refreshJellyfinLibrary()} title="Ask Jellyfin to rescan its libraries">
            Refresh Jellyfin
          </button>
        </div>

        {error && <p className="p-3 text-xs text-red-300">{error}</p>}

        {(activeCommands.length > 0 || activeMoves.length > 0) && (
          <div className="p-3 space-y-2">
            {activeCommands.map(c => (
              <ProgressRow key={`c-${c.commandId}`} label={`${c.app === 'sonarr' ? 'Sonarr' : 'Radarr'} · ${c.name}`} status={c.status} />
            ))}
            {activeMoves.map(m => (
              <ProgressRow
                key={m.id}
                label={`${m.destination.includes('/Trash/') ? 'Trash' : 'Move'} · ${m.source.split('/').pop()}`}
                status={m.status}
                percent={m.totalBytes ? Math.round((m.copiedBytes / m.totalBytes) * 100) : 0}
                detail={`${formatBytes(m.copiedBytes)} of ${formatBytes(m.totalBytes)} · ${m.filesDone}/${m.files} files`}
              />
            ))}
          </div>
        )}

        {!loading && items.length === 0 && !error && (
          <p className="p-3 text-sm text-butler-500">Inbox is empty — everything has been filed.</p>
        )}

        {items.map(item => (
          <InboxRow
            key={item.name}
            item={item}
            kind={kind(item)}
            busy={busy.has(item.name)}
            note={notes[item.name]}
            destinations={data?.destinations ?? []}
            dest={dest[item.name] ?? ''}
            onDest={v => setDest(prev => ({ ...prev, [item.name]: v }))}
            onImport={() => doImport([item.name])}
            onMove={key => doMove(item.name, key)}
          />
        ))}
      </div>
    </Section>
  )
}

type Kind = 'new' | 'duplicate' | 'leftover' | 'unknown'

function classify(i: InboxItem): Kind {
  if (i.empty || i.leftover) return 'leftover'
  if (i.suggestion) return i.suggestion.allInLibrary ? 'duplicate' : 'new'
  return 'unknown'
}

function InboxRow({
  item,
  kind,
  busy,
  note,
  destinations,
  dest,
  onDest,
  onImport,
  onMove,
}: {
  item: InboxItem
  kind: Kind
  busy: boolean
  note?: string
  destinations: { key: string; label: string }[]
  dest: string
  onDest: (v: string) => void
  onImport: () => void
  onMove: (key: string) => void
}) {
  const s = item.suggestion
  const rejections = item.sonarr?.rejections?.length ? item.sonarr.rejections : item.radarr?.rejections ?? []
  const appName = s?.app === 'sonarr' ? 'Sonarr' : 'Radarr'

  let description: React.ReactNode = null
  if (kind === 'leftover') {
    description = <span className="text-butler-500">{item.empty ? 'Empty folder' : 'No video left — only nfo/txt/screens'}</span>
  } else if (s) {
    description = (
      <>
        <span className="text-accent-light">{appName}</span> · {s.titles.join(', ') || 'recognised'}
        {s.episodes ? ` · ${s.episodes} episode${s.episodes === 1 ? '' : 's'}` : ''}
        {kind === 'duplicate' && <span className="text-butler-500"> · already in the library</span>}
        {kind === 'new' && s.inLibrary > 0 && <span className="text-butler-500"> · {s.inLibrary} of {s.matched} already in the library</span>}
        {s.partial && <span className="text-yellow-300"> · {s.matched} of {s.files} files recognised</span>}
      </>
    )
  } else {
    description = <span className="text-butler-500">Not recognised{rejections.length ? `: ${rejections.join('; ')}` : ''}</span>
  }

  return (
    <div className="p-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm text-butler-100 truncate" title={item.name}>{item.name}</p>
          <p className="text-[11px] text-butler-500 tabular-nums">
            {formatBytes(item.bytes)} · {formatAge(item.ageDays)}
            {item.seeding && <Badge tone="warning">seeding</Badge>}
          </p>
          <p className="text-xs text-butler-300 mt-1">{description}</p>
          {note && <p className="text-xs text-butler-400 mt-1">{note}</p>}
        </div>

        <div className="flex flex-col items-end gap-1.5 shrink-0">
          {kind === 'new' && (
            <button className="btn btn-primary text-xs py-1.5" disabled={busy} onClick={onImport}>
              {busy ? 'Working…' : item.seeding ? 'Import (copy)' : 'Import'}
            </button>
          )}
          {kind === 'duplicate' && (
            <>
              <button className="btn btn-secondary text-xs py-1.5" disabled={busy || item.seeding} onClick={() => onMove('trash')} title={item.seeding ? 'Still seeding — remove the torrent first' : 'Move to Downloads/Trash'}>
                {busy ? 'Working…' : 'Trash'}
              </button>
              <button className="btn btn-ghost text-[11px] py-1" disabled={busy} onClick={onImport} title={`${appName} will replace the library file with this one`}>
                Import anyway
              </button>
            </>
          )}
          {kind === 'leftover' && (
            <button className="btn btn-secondary text-xs py-1.5" disabled={busy || item.seeding} onClick={() => onMove('trash')}>
              {busy ? 'Working…' : 'Trash'}
            </button>
          )}
          {kind === 'unknown' && (
            <div className="flex items-center gap-2">
              <select className="input py-1.5 px-2 text-xs w-44" value={dest} onChange={e => onDest(e.target.value)}>
                <option value="">Choose destination…</option>
                {destinations.map(d => (
                  <option key={d.key} value={d.key}>{d.label}</option>
                ))}
              </select>
              <button className="btn btn-secondary text-xs py-1.5" disabled={busy || !dest || item.seeding} onClick={() => onMove(dest)} title={item.seeding ? 'Still seeding — remove the torrent first' : undefined}>
                Move
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Badge({ tone, children }: { tone: 'warning' | 'muted'; children: string }) {
  const cls = tone === 'warning' ? 'bg-yellow-500/15 text-yellow-300' : 'bg-butler-700 text-butler-400'
  return <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide ${cls}`}>{children}</span>
}

function ProgressRow({ label, status, percent, detail }: { label: string; status: string; percent?: number; detail?: string }) {
  const done = status === 'completed' || status === 'done'
  const failed = status === 'failed'
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="text-butler-200 truncate pr-3">{label}</span>
        <span className={`tabular-nums ${failed ? 'text-red-300' : done ? 'text-green-400' : 'text-butler-400'}`}>
          {percent !== undefined ? `${percent}%` : status}
        </span>
      </div>
      {percent !== undefined && (
        <div className="w-full h-1 rounded-full bg-accent/15 mt-1">
          <div className="h-1 rounded-full bg-accent transition-all" style={{ width: `${percent}%` }} />
        </div>
      )}
      {detail && <p className="text-[11px] text-butler-500 mt-0.5">{detail}</p>}
    </div>
  )
}
