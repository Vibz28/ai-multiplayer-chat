import type { CSSProperties, RefObject } from 'react'

import { MarkdownMermaid } from '../../../components/MarkdownMermaid'
import type { ChatMessage } from '../../../types'

type TranscriptPanelProps = {
  messages: ChatMessage[]
  expandedReasoning: Record<string, boolean>
  transcriptRef: RefObject<HTMLDivElement | null>
  onToggleReasoning: (messageId: string) => void
}

function profileHue(profileId: string): number {
  let hash = 0
  for (let i = 0; i < profileId.length; i += 1) {
    hash = (hash * 31 + profileId.charCodeAt(i)) % 360
  }
  return hash
}

export function TranscriptPanel({
  messages,
  expandedReasoning,
  transcriptRef,
  onToggleReasoning,
}: TranscriptPanelProps) {
  return (
    <article className="transcript-panel">
      <div className="panel-heading">
        <h2>Conversation</h2>
        <p>Live stream of user, assistant, and reasoning output.</p>
      </div>
      <div className="message-list" ref={transcriptRef}>
        {messages.length === 0 && <p className="empty">No chat messages yet.</p>}
        {messages.map((message) => {
          const hue = profileHue(message.senderProfileId)
          const cardStyle = { '--sender-hue': `${hue}deg` } as CSSProperties
          const deliveryClass = message.deliveryMode === 'direct' ? 'delivery-direct' : 'delivery-thread'
          const aiClass = message.includeAi === false ? 'ai-disabled' : 'ai-enabled'

          return (
            <article
              key={message.id}
              className={`message-card ${message.kind} ${deliveryClass} ${aiClass}`}
              style={cardStyle}
            >
              <header>
                <div>
                  <strong>{message.senderProfileId}</strong>
                  <span>{message.senderRole}</span>
                </div>
                <time>{new Date(message.createdAt).toLocaleTimeString()}</time>
              </header>

              <div className="message-badges">
                {message.kind === 'user' && (
                  <>
                    <span>{message.deliveryMode === 'direct' ? 'private' : 'group'}</span>
                    <span>{message.includeAi === false ? 'human-only' : 'AI-enabled'}</span>
                  </>
                )}
                {message.kind === 'assistant' && <span>{message.complete ? 'complete' : 'streaming'}</span>}
                {message.kind === 'system' && <span>system</span>}
              </div>

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
                </p>
              )}

              {message.kind === 'assistant' && (
                <div className="assistant-meta">
                  <button type="button" className="ghost" onClick={() => onToggleReasoning(message.id)}>
                    {expandedReasoning[message.id] ? 'Hide reasoning' : 'Show reasoning'}
                  </button>
                </div>
              )}

              {message.kind === 'assistant' && expandedReasoning[message.id] && (
                <pre className="reasoning-box">
                  {message.reasoning || '(waiting for reasoning stream or tool calls)'}
                </pre>
              )}
            </article>
          )
        })}
      </div>
    </article>
  )
}
