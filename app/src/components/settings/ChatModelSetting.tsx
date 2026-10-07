import { useEffect, useState } from 'react'
import { getChatModel, setChatModel, type ChatModelSettings } from '../../services/api'

/** Admin-only: which Claude model Butler chats with, for the whole household. */
export default function ChatModelSetting() {
  const [state, setState] = useState<ChatModelSettings | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getChatModel().then(setState).catch(err => setError(err instanceof Error ? err.message : 'Failed to load'))
  }, [])

  async function choose(model: string | null) {
    if (!state || (state.selected ?? null) === model) return
    setSaving(model ?? 'default')
    setError(null)
    try {
      setState(await setChatModel(model))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(null)
    }
  }

  const choices = state
    ? [
        ...state.options.map(o => ({ id: o.id as string | null, label: o.label, description: o.description })),
        {
          id: null,
          label: 'Server default',
          description: `ANTHROPIC_MODEL in butler/.env (${state.serverDefault}).`,
        },
      ]
    : []

  return (
    <section className="card p-4">
      <h2 className="text-sm font-medium text-butler-400 uppercase tracking-wide mb-1">
        Butler's model
        <span className="text-butler-600 ml-2 text-xs normal-case">admin · everyone</span>
      </h2>
      <p className="text-xs text-butler-500 mb-3">
        The Claude model Butler uses for chat, voice and automations. Takes effect on the next message.
      </p>

      {!state && !error && <p className="text-sm text-butler-500">Loading…</p>}

      <div className="space-y-2" role="radiogroup" aria-label="Butler's model">
        {choices.map(choice => {
          const active = (state?.selected ?? null) === choice.id
          return (
            <button
              key={choice.id ?? 'default'}
              role="radio"
              aria-checked={active}
              onClick={() => choose(choice.id)}
              disabled={saving !== null}
              className={`w-full text-left rounded-lg border px-3 py-2 transition-colors disabled:opacity-60 ${
                active ? 'border-accent bg-accent/10' : 'border-butler-700 hover:border-butler-500'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm text-butler-100">{choice.label}</span>
                <span className="text-xs text-butler-400">
                  {saving === (choice.id ?? 'default') ? 'Saving…' : active ? 'In use' : ''}
                </span>
              </div>
              <div className="text-xs text-butler-500 mt-0.5">{choice.description}</div>
            </button>
          )
        })}
      </div>

      {error && <p className="text-xs text-red-400 mt-2" role="alert">{error}</p>}
    </section>
  )
}
