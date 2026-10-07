import { create } from 'zustand'
import { approveAction, getPendingApprovals, rejectAction } from '../services/api'
import type { ApprovalResult, PendingApproval } from '../types/conversation'

/**
 * Approval store - drafted emails / calendar changes waiting for the user.
 *
 * Butler can only draft these; nothing is sent or changed until the user taps
 * Approve here, which calls the API directly (never through the model).
 */

const OUTCOME_VISIBLE_MS = 6000

interface ApprovalState {
  items: PendingApproval[]
  busy: Record<string, boolean>
  outcomes: Record<string, ApprovalResult>

  fetch: () => Promise<void>
  add: (approval: PendingApproval) => void
  decide: (id: string, approve: boolean) => Promise<void>
  dismiss: (id: string) => void
}

export const useApprovalStore = create<ApprovalState>()((set, get) => ({
  items: [],
  busy: {},
  outcomes: {},

  fetch: async () => {
    try {
      const { approvals } = await getPendingApprovals()
      // Keep cards that are showing an outcome until they're dismissed.
      const { items, outcomes } = get()
      const shown = items.filter(a => outcomes[a.id] && !approvals.some(p => p.id === a.id))
      set({ items: [...approvals, ...shown] })
    } catch {
      // Not fatal: cards also arrive through the chat stream.
    }
  },

  add: (approval) => {
    if (get().items.some(a => a.id === approval.id)) return
    set(state => ({ items: [...state.items, approval] }))
  },

  decide: async (id, approve) => {
    set(state => ({ busy: { ...state.busy, [id]: true } }))
    let outcome: ApprovalResult
    try {
      outcome = approve ? await approveAction(id) : await rejectAction(id)
    } catch (err) {
      outcome = { id, status: 'failed', result: err instanceof Error ? err.message : 'Something went wrong' }
    }
    set(state => ({
      busy: { ...state.busy, [id]: false },
      outcomes: { ...state.outcomes, [id]: outcome },
    }))
    // 'pending' = nothing happened yet (e.g. Google needs reconnecting): the card
    // stays with its buttons. Successes and cancellations fade; failures stay.
    if (outcome.status === 'done' || outcome.status === 'rejected') {
      setTimeout(() => get().dismiss(id), OUTCOME_VISIBLE_MS)
    }
  },

  dismiss: (id) => {
    set(state => {
      const outcomes = { ...state.outcomes }
      const busy = { ...state.busy }
      delete outcomes[id]
      delete busy[id]
      return { items: state.items.filter(a => a.id !== id), outcomes, busy }
    })
  },
}))
