import type { FormEvent } from 'react'

import type { ConversationSummary } from '../../../types'

type ConversationSidebarProps = {
  conversations: ConversationSummary[]
  activeApplicationId: string
  applicationId: string
  applicationIdInput: string
  inviteStatus: string
  shareUrl: string
  onApplicationIdInputChange: (value: string) => void
  onAttachSession: (event: FormEvent) => Promise<void>
  onQuickStartSession: () => Promise<void>
  onOpenConversation: (applicationId: string) => Promise<void>
  onCopyShareUrl: () => Promise<void>
  onOpenShareUrl: () => void
}

function relativeTime(isoDate: string): string {
  const now = Date.now()
  const then = new Date(isoDate).getTime()
  const diffMs = Math.max(0, now - then)
  const minutes = Math.floor(diffMs / 60000)
  if (minutes < 1) {
    return 'just now'
  }
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function compactId(value: string): string {
  if (!value) {
    return 'No active session'
  }
  if (value.length <= 20) {
    return value
  }
  return `${value.slice(0, 9)}…${value.slice(-7)}`
}

export function ConversationSidebar({
  conversations,
  activeApplicationId,
  applicationId,
  applicationIdInput,
  inviteStatus,
  shareUrl,
  onApplicationIdInputChange,
  onAttachSession,
  onQuickStartSession,
  onOpenConversation,
  onCopyShareUrl,
  onOpenShareUrl,
}: ConversationSidebarProps) {
  return (
    <aside className="thread-sidebar panel">
      <div className="sidebar-head">
        <h2>Conversations</h2>
        <button type="button" onClick={() => void onQuickStartSession()} className="new-chat-btn">
          Start chat session
        </button>
      </div>

      <section className="quick-guide">
        <h3>Multiplayer Quick Start</h3>
        <ol className="guide-list">
          <li>Start a chat session to generate an application ID.</li>
          <li>Copy the invite link and open it in an incognito tab.</li>
          <li>Toggle incognito in the top-right and choose a profile icon.</li>
          <li>Join and send messages in the same thread from both tabs.</li>
        </ol>
      </section>

      <section className="session-pillbox" aria-live="polite">
        <p className="session-id">Active app: {compactId(applicationId)}</p>
        <div className="button-row compact">
          <button type="button" className="ghost" onClick={() => void onCopyShareUrl()} disabled={!shareUrl}>
            Copy invite link
          </button>
          <button type="button" className="ghost" onClick={onOpenShareUrl} disabled={!shareUrl}>
            Open invite tab
          </button>
        </div>
        {inviteStatus && <p className="hint-text">{inviteStatus}</p>}
      </section>

      <form className="join-form" onSubmit={(event) => void onAttachSession(event)}>
        <label htmlFor="joinById">Join by application ID</label>
        <div className="join-row">
          <input
            id="joinById"
            value={applicationIdInput}
            onChange={(event) => onApplicationIdInputChange(event.target.value)}
            placeholder="app_xxx"
          />
          <button type="submit" className="ghost">
            Join
          </button>
        </div>
      </form>

      <details className="conversation-list" open>
        <summary>Recent chats ({conversations.length})</summary>
        {conversations.length === 0 ? (
          <p className="empty">No conversations yet. Start your first chat session.</p>
        ) : (
          <ul>
            {conversations.map((conversation) => (
              <li key={conversation.applicationId}>
                <button
                  type="button"
                  className={
                    conversation.applicationId === activeApplicationId
                      ? 'thread-item active'
                      : 'thread-item'
                  }
                  onClick={() => void onOpenConversation(conversation.applicationId)}
                >
                  <strong>{conversation.title}</strong>
                  <p>{conversation.summary}</p>
                  <div className="thread-meta">
                    <span>{relativeTime(conversation.lastUpdated)}</span>
                    <span>{conversation.isIncognito ? 'incognito' : 'standard'}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </details>
    </aside>
  )
}
