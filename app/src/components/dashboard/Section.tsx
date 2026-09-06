import type { ReactNode } from 'react'

/** Consistent section chrome: small-caps title, optional right-hand slot. */
export default function Section({
  title,
  aside,
  children,
}: {
  title: string
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold text-butler-400 uppercase tracking-wider">{title}</h2>
        {aside && <div className="text-xs text-butler-500">{aside}</div>}
      </div>
      {children}
    </section>
  )
}
