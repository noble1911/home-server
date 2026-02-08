import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github-dark.css'

const REMARK_PLUGINS = [remarkGfm]
const REHYPE_PLUGINS = [rehypeHighlight]

interface MarkdownContentProps {
  content: string
}

function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <div className="text-sm">
      <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={REHYPE_PLUGINS}
      components={{
        p: ({ children }) => (
          <p className="mb-2 last:mb-0">{children}</p>
        ),

        pre: ({ children }) => (
          <pre className="bg-butler-900/80 rounded-lg p-3 overflow-x-auto my-2 text-[0.8125rem] leading-relaxed">
            {children}
          </pre>
        ),

        code: ({ className, children, ...props }) => {
          const isBlock = /^hljs\b|^language-/.test(className || '')
          if (isBlock) {
            return (
              <code className={`${className} !bg-transparent`} {...props}>
                {children}
              </code>
            )
          }
          return (
            <code
              className="bg-butler-900 px-1.5 py-0.5 rounded text-accent-light text-[0.8125rem]"
              {...props}
            >
              {children}
            </code>
          )
        },

        ul: ({ children }) => (
          <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>
        ),
        li: ({ children }) => <li>{children}</li>,

        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent-light underline hover:text-accent"
          >
            {children}
          </a>
        ),

        strong: ({ children }) => (
          <strong className="font-semibold text-butler-50">{children}</strong>
        ),

        em: ({ children }) => <em className="italic">{children}</em>,

        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-butler-600 pl-3 my-2 text-butler-300">
            {children}
          </blockquote>
        ),

        h1: ({ children }) => (
          <h1 className="text-lg font-bold mb-2">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-base font-bold mb-2">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-sm font-bold mb-1">{children}</h3>
        ),

        hr: () => <hr className="border-butler-600 my-3" />,

        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="min-w-full text-xs border border-butler-700">
              {children}
            </table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-butler-900/50">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1 border border-butler-700 text-left font-semibold">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-2 py-1 border border-butler-700">{children}</td>
        ),
      }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export default memo(MarkdownContent)
