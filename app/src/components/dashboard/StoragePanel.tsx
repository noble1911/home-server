import type { StorageDrive, SystemStorageResponse } from '../../services/api'
import Meter, { severityFor } from './Meter'
import Section from './Section'

const ROLE_LABEL: Record<string, string> = {
  system: 'System',
  downloads: 'Downloads',
  library: 'Library',
}

/**
 * Storage — the two media drives as one pool, then each drive with what's on it.
 * Falls back to the old single-volume view when the host agent is down.
 */
export default function StoragePanel({ storage }: { storage: SystemStorageResponse | null }) {
  const drives = storage?.drives?.filter(d => d.mounted) ?? []
  const pool = storage?.pool ?? null
  const sizesAt = storage?.categoriesAt ? new Date(storage.categoriesAt * 1000) : null

  if (!drives.length) {
    return (
      <Section title="Storage">
        <div className="card p-4 space-y-3">
          {storage && storage.volumes.length > 0 ? (
            storage.volumes.map(v => (
              <Meter key={v.name} label={v.name} percent={v.percent} value={`${v.usedFormatted} / ${v.totalFormatted}`} hint={`${v.freeFormatted} free`} warn={80} crit={90} />
            ))
          ) : (
            <p className="text-sm text-butler-500">No volumes detected</p>
          )}
        </div>
      </Section>
    )
  }

  const media = drives.filter(d => d.role === 'downloads' || d.role === 'library')
  const system = drives.filter(d => d.role === 'system')

  return (
    <Section title="Storage" aside={sizesAt ? `folder sizes as of ${sizesAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : undefined}>
      {storage?.diskAccess === false && (
        <div className="card p-3 mb-4 border-yellow-500/30 bg-yellow-500/10 text-xs text-yellow-200">
          <p className="font-medium">macOS is blocking the host agent from reading the external drives.</p>
          <p className="text-yellow-200/80 mt-1">
            Folder sizes and moves will work once you grant Full Disk Access: System Settings → Privacy &amp; Security → Full Disk Access → + → select
            {' '}<code className="text-yellow-100">{storage.agentPython ?? 'the agent\'s Python.app'}</code> (the app bundle; the bin stub is greyed out), then restart the agent.
          </p>
        </div>
      )}
      {pool && (
        <div className="card p-4 mb-4">
          <div className="flex items-end justify-between gap-4 mb-3">
            <div>
              <p className="text-[11px] text-butler-500 uppercase tracking-wide">Media drives together</p>
              <p className="text-3xl font-semibold text-butler-100 tabular-nums leading-tight">
                {pool.usedFormatted}
                <span className="text-base font-normal text-butler-400"> of {pool.totalFormatted}</span>
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm text-butler-200 tabular-nums">{pool.freeFormatted} free</p>
              <p className="text-[11px] text-butler-500">{pool.drives.join(' + ')}</p>
            </div>
          </div>
          <Meter label="Used" percent={pool.percent} value={`${pool.percent}%`} warn={80} crit={90} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {media.map(d => <DriveCard key={d.name} drive={d} />)}
      </div>
      {system.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          {system.map(d => <DriveCard key={d.name} drive={d} compact />)}
        </div>
      )}
    </Section>
  )
}

function DriveCard({ drive, compact = false }: { drive: StorageDrive; compact?: boolean }) {
  const pct = drive.percent ?? 0
  const sev = severityFor(pct, 80, 90)
  const cats = (drive.categories ?? []).filter(c => c.exists)
  const local = cats.filter(c => !c.linkedTo)
  const linked = cats.filter(c => c.linkedTo)

  return (
    <div className={`card p-4 ${sev === 'critical' ? 'border-red-500/40' : sev === 'warning' ? 'border-yellow-500/30' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-butler-100">{drive.name}</h3>
          <p className="text-[11px] text-butler-500">{drive.path}</p>
        </div>
        {drive.role && (
          <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-butler-700 text-butler-300">
            {ROLE_LABEL[drive.role] ?? drive.role}
          </span>
        )}
      </div>

      <Meter
        label="Used"
        percent={pct}
        value={`${drive.usedFormatted} / ${drive.totalFormatted}`}
        hint={`${drive.freeFormatted} free`}
        warn={80}
        crit={90}
      />

      {sev !== 'ok' && (
        <p className={`text-xs mt-2 ${sev === 'critical' ? 'text-red-300' : 'text-yellow-300'}`}>
          {sev === 'critical' ? 'Nearly full.' : 'Getting full.'} New downloads should go to a drive with space.
        </p>
      )}

      {!compact && local.length > 0 && (
        <ul className="mt-3 divide-y divide-butler-700/60">
          {local
            .slice()
            .sort((a, b) => (b.bytes ?? 0) - (a.bytes ?? 0))
            .map(c => (
              <li key={c.label} className="flex justify-between py-1.5 text-xs">
                <span className="text-butler-300">{c.label}</span>
                <span className="text-butler-200 tabular-nums">{c.formatted ?? 'measuring…'}</span>
              </li>
            ))}
        </ul>
      )}
      {compact && local.length > 0 && (
        <p className="text-[11px] text-butler-500 mt-2">
          {local.map(c => `${c.label} ${c.formatted ?? '…'}`).join(' · ')}
        </p>
      )}
      {linked.length > 0 && (
        <p className="text-[11px] text-butler-500 mt-2">
          {linked.map(c => c.label).join(', ')} {linked.length > 1 ? 'are' : 'is'} a link to{' '}
          {linkedDriveName(linked[0].linkedTo!)}
        </p>
      )}
    </div>
  )
}

function linkedDriveName(target: string): string {
  const m = target.match(/^\/Volumes\/([^/]+)/)
  return m ? m[1] : target
}
