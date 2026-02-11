import { useState } from 'react'
import ExamplePrompt from './ExamplePrompt'

export interface TutorialTool {
  name: string
  description: string
  examples: string[]
}

export interface CategoryData {
  id: string
  title: string
  description: string
  icon: string
  permission?: string
  tools: TutorialTool[]
}

interface CategorySectionProps {
  category: CategoryData
  defaultOpen?: boolean
}

export default function CategorySection({ category, defaultOpen = false }: CategorySectionProps) {
  const [expanded, setExpanded] = useState(defaultOpen)

  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-butler-800/50 transition-colors"
      >
        <span className="text-2xl shrink-0">{category.icon}</span>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-butler-200">{category.title}</h3>
          <p className="text-xs text-butler-400 truncate">{category.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {category.permission && (
            <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 bg-butler-700/50 rounded text-[10px] text-butler-400">
              <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              {category.permission}
            </span>
          )}
          <svg
            className={`w-5 h-5 text-butler-500 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-butler-700/50">
          {category.tools.map((tool) => (
            <div key={tool.name} className="pt-3 space-y-2">
              <div>
                <h4 className="text-sm font-medium text-butler-300">{tool.name}</h4>
                <p className="text-xs text-butler-400">{tool.description}</p>
              </div>
              <div className="space-y-1.5">
                {tool.examples.map((example) => (
                  <ExamplePrompt key={example} prompt={example} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
