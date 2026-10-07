import { useState } from 'react'
import { useApprovalStore } from '../../stores/approvalStore'
import type { PendingApproval } from '../../types/conversation'

/**
 * Drafted emails and calendar changes waiting for the user's approval.
 * Approving calls the API directly — Butler itself can't send or change anything.
 */
export default function ApprovalCards() {
  const items = useApprovalStore(s => s.items)
  if (items.length === 0) return null

  return (
    <div className="space-y-2 pb-2 max-h-[45vh] overflow-y-auto">
      {items.map(item => <ApprovalCard key={item.id} approval={item} />)}
    </div>
  )
}

function ApprovalCard({ approval }: { approval: PendingApproval }) {
  const busy = useApprovalStore(s => s.busy[approval.id])
  const outcome = useApprovalStore(s => s.outcomes[approval.id])
  const decide = useApprovalStore(s => s.decide)
  const dismiss = useApprovalStore(s => s.dismiss)
  const [showBody, setShowBody] = useState(true)

  const isEmail = approval.kind.startsWith('gmail.')
  const approveLabel = isEmail ? 'Send' : 'Approve'

  if (outcome && outcome.status !== 'pending') {
    const ok = outcome.status === 'done'
    const cancelled = outcome.status === 'rejected'
    return (
      <div
        className={`rounded-lg border px-3 py-2 text-sm flex items-start justify-between gap-2 ${
          ok ? 'border-green-700/50 bg-green-900/20 text-green-200'
            : cancelled ? 'border-butler-700 bg-butler-800/60 text-butler-300'
            : 'border-red-800/60 bg-red-900/20 text-red-200'
        }`}
        role="status"
      >
        <span>{ok ? '✓ ' : cancelled ? '' : '⚠ '}{outcome.result}</span>
        <button
          onClick={() => dismiss(approval.id)}
          className="text-xs opacity-70 hover:opacity-100 shrink-0"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-accent/40 bg-butler-800/80 px-3 py-2.5">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="text-sm font-medium text-butler-100">{approval.title}</div>
        <div className="text-[11px] text-butler-400">Needs your OK</div>
      </div>

      <dl className="text-xs space-y-0.5">
        {approval.fields.map(([label, value]) => (
          <div key={label} className="flex gap-2">
            <dt className="text-butler-400 shrink-0 w-16">{label}</dt>
            <dd className="text-butler-200 break-words min-w-0">{value}</dd>
          </div>
        ))}
      </dl>

      {approval.body && (
        <div className="mt-2">
          <button
            onClick={() => setShowBody(v => !v)}
            className="text-[11px] text-butler-400 hover:text-butler-200"
          >
            {showBody ? 'Hide message' : 'Show message'}
          </button>
          {showBody && (
            <div className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap rounded bg-butler-900/70 px-2 py-1.5 text-xs text-butler-200">
              {approval.body}
            </div>
          )}
        </div>
      )}

      {outcome?.status === 'pending' && (
        <div className="mt-2 text-xs text-amber-300" role="status">{outcome.result}</div>
      )}

      <div className="mt-2.5 flex justify-end gap-2">
        <button
          onClick={() => decide(approval.id, false)}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-xs bg-butler-700 text-butler-200 hover:bg-butler-600 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={() => decide(approval.id, true)}
          disabled={busy}
          className="px-3 py-1.5 rounded-lg text-xs bg-accent text-white hover:bg-accent/80 disabled:opacity-50"
        >
          {busy ? (isEmail ? 'Sending…' : 'Working…') : approveLabel}
        </button>
      </div>
    </div>
  )
}
