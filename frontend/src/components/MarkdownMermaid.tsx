import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type Segment =
  | {
      kind: 'markdown'
      content: string
    }
  | {
      kind: 'mermaid'
      content: string
    }

const MERMAID_BLOCK_PATTERN = /```mermaid\s*([\s\S]*?)```/gi

let mermaidInitialized = false
let mermaidPromise: Promise<typeof import('mermaid').default> | null = null

async function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((module) => module.default)
  }
  const mermaid = await mermaidPromise
  if (!mermaidInitialized) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      suppressErrorRendering: true,
      theme: 'base',
      fontFamily: "'IBM Plex Sans', sans-serif",
    })
    mermaidInitialized = true
  }
  return mermaid
}

function splitSegments(markdown: string): Segment[] {
  const source = markdown || ''
  const segments: Segment[] = []
  let cursor = 0
  for (const match of source.matchAll(MERMAID_BLOCK_PATTERN)) {
    const matchStart = match.index ?? 0
    const matchEnd = matchStart + match[0].length
    if (matchStart > cursor) {
      segments.push({
        kind: 'markdown',
        content: source.slice(cursor, matchStart),
      })
    }
    segments.push({
      kind: 'mermaid',
      content: match[1].trim(),
    })
    cursor = matchEnd
  }
  if (cursor < source.length) {
    segments.push({
      kind: 'markdown',
      content: source.slice(cursor),
    })
  }
  if (segments.length === 0) {
    segments.push({ kind: 'markdown', content: source })
  }
  return segments
}

function candidateMermaidSources(rawCode: string): string[] {
  const trimmed = rawCode.trim()
  const cleaned = trimmed.replace(/^```/, '').replace(/```$/, '').trim()
  const candidates = [cleaned]
  if (!/^graph\s+/i.test(cleaned) && !/^flowchart\s+/i.test(cleaned)) {
    candidates.push(`flowchart TD\n${cleaned}`)
  }
  return [...new Set(candidates)]
}

function MermaidDiagram({ source }: { source: string }) {
  const [svg, setSvg] = useState<string>('')
  const [errorText, setErrorText] = useState<string>('')

  useEffect(() => {
    let cancelled = false

    async function renderDiagram() {
      const candidates = candidateMermaidSources(source)
      let lastError = 'unknown mermaid render failure'
      const mermaid = await loadMermaid()
      for (const candidate of candidates) {
        try {
          const renderId = `mermaid-${crypto.randomUUID()}`
          const result = await mermaid.render(renderId, candidate)
          if (cancelled) {
            return
          }
          setSvg(result.svg)
          setErrorText('')
          return
        } catch (error) {
          lastError = error instanceof Error ? error.message : String(error)
        }
      }
      if (!cancelled) {
        setSvg('')
        setErrorText(lastError)
      }
    }

    renderDiagram()
    return () => {
      cancelled = true
    }
  }, [source])

  if (svg) {
    return (
      <section className="mermaid-shell" aria-label="Rendered Mermaid diagram">
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      </section>
    )
  }

  return (
    <section className="mermaid-fallback" aria-label="Mermaid fallback">
      <p className="mermaid-error">Mermaid render failed: {errorText}</p>
      <pre>{source}</pre>
    </section>
  )
}

export function MarkdownMermaid({ markdown }: { markdown: string }) {
  const segments = useMemo(() => splitSegments(markdown), [markdown])

  return (
    <div className="markdown-mermaid">
      {segments.map((segment, index) =>
        segment.kind === 'markdown' ? (
          <ReactMarkdown key={`md-${index}`} remarkPlugins={[remarkGfm]}>
            {segment.content}
          </ReactMarkdown>
        ) : (
          <MermaidDiagram key={`mm-${index}`} source={segment.content} />
        ),
      )}
    </div>
  )
}
