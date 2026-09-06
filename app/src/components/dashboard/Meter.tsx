/**
 * Meter — a single ratio against a limit.
 *
 * Fill carries severity (accent → warning → critical) and the label always
 * says the state in words too, so colour is never the only signal.
 */
export type Severity = 'ok' | 'warning' | 'critical'

export function severityFor(percent: number, warn = 70, crit = 85): Severity {
  if (percent >= crit) return 'critical'
  if (percent >= warn) return 'warning'
  return 'ok'
}

const FILL: Record<Severity, string> = {
  ok: 'bg-accent',
  warning: 'bg-yellow-400',
  critical: 'bg-red-400',
}
const TRACK: Record<Severity, string> = {
  ok: 'bg-accent/15',
  warning: 'bg-yellow-400/15',
  critical: 'bg-red-400/15',
}
const TEXT: Record<Severity, string> = {
  ok: 'text-butler-200',
  warning: 'text-yellow-300',
  critical: 'text-red-300',
}

interface MeterProps {
  label: string
  percent: number | null | undefined
  value?: string
  hint?: string
  warn?: number
  crit?: number
  size?: 'sm' | 'md'
}

export default function Meter({ label, percent, value, hint, warn, crit, size = 'md' }: MeterProps) {
  const p = typeof percent === 'number' && Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : null
  const sev = p === null ? 'ok' : severityFor(p, warn, crit)
  const h = size === 'sm' ? 'h-1' : 'h-1.5'
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-xs mb-1">
        <span className="text-butler-400 truncate">{label}</span>
        <span className={`${TEXT[sev]} tabular-nums whitespace-nowrap`}>
          {value ?? (p === null ? '--' : `${p}%`)}
          {sev !== 'ok' && p !== null && (
            <span className="ml-1.5 text-[10px] uppercase tracking-wide opacity-80">{sev === 'critical' ? 'high' : 'warm'}</span>
          )}
        </span>
      </div>
      <div className={`w-full rounded-full ${h} ${TRACK[sev]}`} role="meter" aria-valuenow={p ?? undefined} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className={`${h} rounded-full transition-all duration-500 ${FILL[sev]}`} style={{ width: `${p ?? 0}%` }} />
      </div>
      {hint && <p className="text-[11px] text-butler-500 mt-0.5">{hint}</p>}
    </div>
  )
}
