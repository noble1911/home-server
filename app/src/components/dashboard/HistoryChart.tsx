import { useMemo, useRef, useState } from 'react'

/**
 * Small time-series line chart in plain SVG (no library).
 *
 * One percent axis, up to three series, thin 2px lines, recessive grid, a
 * legend (identity is never colour-alone), and a crosshair + tooltip on hover.
 */
export interface Series {
  key: string
  label: string
  color: string        // stroke; also used for the legend swatch
  points: { t: number; v: number }[]
}

interface Props {
  series: Series[]
  minutes: number
  max?: number         // axis top (default 100)
  height?: number
  unit?: string
}

const PAD = { top: 8, right: 8, bottom: 20, left: 30 }

export default function HistoryChart({ series, minutes, max = 100, height = 140, unit = '%' }: Props) {
  const [hover, setHover] = useState<number | null>(null) // timestamp
  const svgRef = useRef<SVGSVGElement>(null)
  const width = 600 // viewBox units; scales with the container

  const now = Math.floor(Date.now() / 1000)
  const t0 = now - minutes * 60
  const t1 = now

  const x = (t: number) => PAD.left + ((t - t0) / (t1 - t0)) * (width - PAD.left - PAD.right)
  const y = (v: number) => PAD.top + (1 - Math.min(v, max) / max) * (height - PAD.top - PAD.bottom)

  const paths = useMemo(
    () =>
      series.map(s => {
        const pts = s.points.filter(p => p.t >= t0 && p.t <= t1)
        if (pts.length < 2) return { key: s.key, d: '', area: '' }
        const d = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')
        const area = `${d} L${x(pts[pts.length - 1].t).toFixed(1)},${y(0).toFixed(1)} L${x(pts[0].t).toFixed(1)},${y(0).toFixed(1)} Z`
        return { key: s.key, d, area }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [series, minutes, max, height],
  )

  const hasData = series.some(s => s.points.length >= 2)

  // Hover: nearest sample per series at the hovered timestamp
  const hoverRows = useMemo(() => {
    if (hover === null) return []
    return series.map(s => {
      let best: { t: number; v: number } | null = null
      for (const p of s.points) {
        if (!best || Math.abs(p.t - hover) < Math.abs(best.t - hover)) best = p
      }
      return { label: s.label, color: s.color, v: best && Math.abs(best.t - hover) < 60 ? best.v : null }
    })
  }, [hover, series])

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const px = ((e.clientX - rect.left) / rect.width) * width
    const frac = (px - PAD.left) / (width - PAD.left - PAD.right)
    if (frac < 0 || frac > 1) return setHover(null)
    setHover(t0 + frac * (t1 - t0))
  }

  const gridVals = [0, 25, 50, 75, 100].map(v => (v / 100) * max)
  const ticks = minutes <= 10 ? [10, 5, 0] : minutes <= 30 ? [30, 20, 10, 0] : [60, 45, 30, 15, 0]

  return (
    <div>
      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto select-none"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
          role="img"
          aria-label={series.map(s => s.label).join(', ')}
        >
          {/* grid */}
          {gridVals.map(v => (
            <g key={v}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} stroke="currentColor" className="text-butler-700" strokeWidth={1} />
              <text x={PAD.left - 4} y={y(v) + 3} textAnchor="end" fontSize={9} className="fill-butler-500">
                {Math.round(v)}{unit}
              </text>
            </g>
          ))}
          {/* time ticks */}
          {ticks.map(m => {
            const t = t1 - m * 60
            return (
              <text key={m} x={x(t)} y={height - 6} textAnchor={m === ticks[0] ? 'start' : m === 0 ? 'end' : 'middle'} fontSize={9} className="fill-butler-500">
                {m === 0 ? 'now' : `-${m}m`}
              </text>
            )
          })}
          {/* series */}
          {series.map((s, i) => (
            <g key={s.key}>
              {paths[i].area && <path d={paths[i].area} fill={s.color} opacity={0.08} />}
              {paths[i].d && <path d={paths[i].d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
            </g>
          ))}
          {/* crosshair */}
          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={height - PAD.bottom} stroke="currentColor" className="text-butler-400" strokeWidth={1} strokeDasharray="3 3" />
          )}
          {!hasData && (
            <text x={width / 2} y={height / 2} textAnchor="middle" fontSize={11} className="fill-butler-500">
              collecting samples…
            </text>
          )}
        </svg>
        {hover !== null && hoverRows.length > 0 && (
          <div className="absolute top-1 right-2 card px-2 py-1.5 text-[11px] space-y-0.5 pointer-events-none">
            <div className="text-butler-500 tabular-nums">{new Date(hover * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
            {hoverRows.map(r => (
              <div key={r.label} className="flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-sm" style={{ background: r.color }} />
                <span className="text-butler-300">{r.label}</span>
                <span className="text-butler-100 tabular-nums ml-auto">{r.v === null ? '--' : `${r.v}${unit}`}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1">
        {series.map(s => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-[11px] text-butler-400">
            <span className="inline-block w-3 h-0.5 rounded" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
