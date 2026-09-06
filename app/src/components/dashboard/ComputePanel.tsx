import type { ContainerUsage, ProcessUsage, SystemStatsResponse } from '../../services/api'
import Meter from './Meter'
import Section from './Section'

/**
 * Compute — the Mac itself next to the Docker VM inside it.
 *
 * The two are different things: containers live in an OrbStack Linux VM with
 * its own RAM ceiling, while Jellyfin, Ollama and OrbStack's own VM process
 * run natively. Both are shown so "why is the Mac slow" has an answer.
 */
export default function ComputePanel({ stats }: { stats: SystemStatsResponse | null }) {
  const host = stats?.host ?? null
  const vmMem = stats?.memory ?? null
  const vmShare = host?.memory.total && vmMem ? Math.round((vmMem.dockerTotal / host.memory.total) * 100) : null

  return (
    <Section
      title="Compute"
      aside={host?.cpu.cores ? `${host.cpu.cores} cores · ${stats?.architecture ?? ''}`.trim() : undefined}
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Mac — bare metal */}
        <div className="card p-4">
          <CardTitle title="Mac mini" subtitle="bare metal — everything, native apps included" />
          {host ? (
            <div className="space-y-3">
              <Meter
                label="CPU"
                percent={host.cpu.percent}
                hint={host.cpu.load ? `load ${host.cpu.load.map(l => l.toFixed(1)).join(' · ')}` : undefined}
              />
              <Meter
                label="Memory"
                percent={host.memory.percent}
                value={`${host.memory.usedFormatted} / ${host.memory.totalFormatted}`}
                warn={80}
                crit={90}
              />
              <Meter
                label="Swap"
                percent={host.swap.percent}
                value={`${host.swap.usedFormatted} / ${host.swap.totalFormatted}`}
                hint={host.swap.percent && host.swap.percent > 50 ? 'Steady swap use means RAM is the constraint' : undefined}
                warn={50}
                crit={80}
              />
              <Row label="Uptime" value={host.uptimeFormatted ?? '--'} />
            </div>
          ) : (
            <p className="text-sm text-butler-500">
              Host agent not reachable. Run <code className="text-butler-300">scripts/16-host-agent.sh</code> on the Mac to see bare-metal numbers.
            </p>
          )}
        </div>

        {/* Docker VM */}
        <div className="card p-4">
          <CardTitle
            title="Docker VM"
            subtitle={vmShare ? `OrbStack Linux VM · holds ${vmShare}% of the Mac's RAM` : 'OrbStack Linux VM running the containers'}
          />
          <div className="space-y-3">
            <Meter label="CPU" percent={stats?.cpu?.percent ?? null} />
            <Meter
              label="Memory"
              percent={vmMem?.dockerPercent ?? null}
              value={vmMem ? `${vmMem.dockerUsedFormatted} / ${vmMem.dockerTotalFormatted}` : undefined}
              warn={80}
              crit={90}
            />
            <Row label="Uptime" value={stats?.uptimeFormatted ?? '--'} />
          </div>
        </div>
      </div>

      {host && (host.apps.length > 0 || host.containers.length > 0) && (
        <div className="card p-4 mt-4">
          <CardTitle title="Who's using it" subtitle="CPU is % of the whole machine; memory is resident" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
            <UsageList
              title="Native apps"
              rows={host.apps.map(a => ({ name: a.name, cpu: a.cpu, mem: a.rss, memFormatted: a.rssFormatted }))}
              totalMem={host.memory.total}
            />
            <UsageList
              title="Containers (top by memory)"
              rows={host.containers.slice(0, 7).map((c: ContainerUsage) => ({ name: c.name, cpu: c.cpu, mem: c.memory, memFormatted: c.memoryFormatted }))}
              totalMem={host.memory.total}
            />
          </div>
          {host.topCpu.length > 0 && (
            <p className="text-[11px] text-butler-500 mt-4">
              Busiest right now: {host.topCpu.slice(0, 3).map((p: ProcessUsage) => `${p.name} ${p.cpu}%`).join(' · ')}
            </p>
          )}
        </div>
      )}
    </Section>
  )
}

function CardTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-sm font-semibold text-butler-100">{title}</h3>
      {subtitle && <p className="text-[11px] text-butler-500">{subtitle}</p>}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-xs pt-1">
      <span className="text-butler-400">{label}</span>
      <span className="text-butler-200 tabular-nums">{value}</span>
    </div>
  )
}

interface UsageRow {
  name: string
  cpu: number | null
  mem: number | null
  memFormatted: string
}

function UsageList({ title, rows, totalMem }: { title: string; rows: UsageRow[]; totalMem: number | null }) {
  return (
    <div>
      <div className="flex justify-between text-[11px] text-butler-500 uppercase tracking-wide mb-2">
        <span>{title}</span>
        <span className="tabular-nums">CPU · RAM</span>
      </div>
      <ul className="space-y-2">
        {rows.length === 0 && <li className="text-xs text-butler-500">nothing to show</li>}
        {rows.map(r => {
          const share = totalMem && r.mem ? Math.min(100, (r.mem / totalMem) * 100) : 0
          return (
            <li key={r.name}>
              <div className="flex justify-between text-xs">
                <span className="text-butler-200 truncate pr-3">{r.name}</span>
                <span className="text-butler-300 tabular-nums whitespace-nowrap">
                  {r.cpu === null ? '--' : `${r.cpu.toFixed(1)}%`} · {r.memFormatted}
                </span>
              </div>
              <div className="w-full h-1 rounded-full bg-butler-700/60 mt-1">
                <div className="h-1 rounded-full bg-accent/70" style={{ width: `${share}%` }} />
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
