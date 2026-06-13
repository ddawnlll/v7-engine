import { Copy, Download, RefreshCw } from 'lucide-react'

type JsonViewerProps = {
  title?: string
  json: unknown
  onCopy?: () => void
  onDownload?: () => void
  onRefresh?: () => void
  meta?: string
}

function highlightJson(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(
      /("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*")(\s*:)?|(-?\d+(?:\.\d+)?)|\b(true|false|null)\b/g,
      (match, stringLiteral, keySuffix, numberLiteral, literalKeyword) => {
        if (stringLiteral) {
          const className = keySuffix ? 'text-stone-300' : 'text-teal-300'
          return `<span class="${className}">${stringLiteral}</span>${keySuffix ?? ''}`
        }
        if (numberLiteral) {
          return `<span class="text-amber-300">${numberLiteral}</span>`
        }
        if (literalKeyword) {
          return `<span class="text-rose-300">${literalKeyword}</span>`
        }
        return match
      },
    )
}

export function JsonViewer({ title, json, onCopy, onDownload, onRefresh, meta }: JsonViewerProps) {
  const content = JSON.stringify(json, null, 2)

  return (
    <div className="min-w-0 rounded-[1.2rem] border border-stone-900/8 bg-white/82 p-3 sm:p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="grid gap-1">
          {title ? <div className="text-sm font-semibold text-stone-950">{title}</div> : null}
          {meta ? <div className="text-sm text-stone-500">{meta}</div> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {onCopy ? (
            <button
              type="button"
              onClick={onCopy}
              className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-3.5 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
            >
              <Copy className="h-4 w-4" strokeWidth={1.8} />
              Copy Full Payload
            </button>
          ) : null}
          {onDownload ? (
            <button
              type="button"
              onClick={onDownload}
              className="inline-flex items-center gap-2 rounded-full border border-stone-900/8 bg-white px-3.5 py-2 text-sm font-semibold text-stone-800 transition hover:bg-stone-950/[0.03]"
            >
              <Download className="h-4 w-4" strokeWidth={1.8} />
              Download JSON
            </button>
          ) : null}
          {onRefresh ? (
            <button
              type="button"
              onClick={onRefresh}
              className="inline-flex items-center gap-2 rounded-full bg-stone-950 px-3.5 py-2 text-sm font-semibold text-stone-50 transition hover:bg-stone-900"
            >
              <RefreshCw className="h-4 w-4" strokeWidth={1.8} />
              Refresh
            </button>
          ) : null}
        </div>
      </div>
      <div className="mt-3 max-h-[22rem] overflow-auto overflow-x-hidden rounded-[1rem] bg-stone-950 px-3 py-3 sm:mt-4 sm:max-h-[28rem] sm:px-4 sm:py-4">
        <pre
          className="min-w-0 whitespace-pre-wrap break-all font-mono text-[11px] leading-5 text-stone-200 [overflow-wrap:anywhere] sm:text-xs sm:leading-6"
          dangerouslySetInnerHTML={{ __html: highlightJson(content) }}
        />
      </div>
    </div>
  )
}
