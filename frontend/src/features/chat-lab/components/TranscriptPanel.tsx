import type { RefObject } from 'react'

import { MarkdownMermaid } from '../../../components/MarkdownMermaid'
import type { ChatMessage } from '../../../types'

type TranscriptPanelProps = {
  messages: ChatMessage[]
  expandedReasoning: Record<string, boolean>
  transcriptRef: RefObject<HTMLDivElement | null>
  onToggleReasoning: (messageId: string) => void
}

export function TranscriptPanel({
  messages,
  expandedReasoning,
  transcriptRef,
  onToggleReasoning,
}: TranscriptPanelProps) {
  return (
    <article className="panel transcript-panel">
      <h2>Transcript</h2>
      <div className="message-list" ref={transcriptRef}>
        {messages.length === 0 && <p className="empty">No chat messages yet.</p>}
        {messages.map((message) => (
          <article key={message.id} className={`message-card ${message.kind}`}>
            <header>
              <div>
                <strong>{message.senderProfileId}</strong>
                <span>{message.senderRole}</span>
              </div>
              <time>{new Date(message.createdAt).toLocaleTimeString()}</time>
            </header>

            {message.kind === 'assistant' ? (
              <MarkdownMermaid markdown={message.content || '_waiting for content stream..._'} />
            ) : (
              <pre>{message.content}</pre>
            )}

            {message.kind !== 'assistant' && message.deliveryMode && (
              <p className="message-meta">
                mode={message.deliveryMode}
                {message.recipientProfileIds && message.recipientProfileIds.length > 0
                  ? ` targets=${message.recipientProfileIds.join(', ')}`
                  : ''}
                {message.includeAi ? ' +ai' : ' no-ai'}
              </p>
            )}

            {message.kind === 'assistant' && (
              <div className="assistant-meta">
                <button type="button" className="ghost" onClick={() => onToggleReasoning(message.id)}>
                  {expandedReasoning[message.id] ? 'Hide reasoning' : 'Show reasoning'}
                </button>
                <span>{message.complete ? 'complete' : 'streaming'}</span>
              </div>
            )}

            {message.kind === 'assistant' && expandedReasoning[message.id] && (
              <pre className="reasoning-box">
                {message.reasoning || '(waiting for reasoning stream or tool calls)'}
              </pre>
            )}
          </article>
        ))}
      </div>
    </article>
  )
}
