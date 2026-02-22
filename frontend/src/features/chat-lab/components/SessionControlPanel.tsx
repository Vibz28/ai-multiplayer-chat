import type { FormEvent } from 'react'

type SessionControlPanelProps = {
  sessionProfileId: string
  sessionRole: string
  applicationIdInput: string
  applicationId: string
  threadId: string | null
  workflowId: string | null
  traceId: string | null
  connectedParticipantCount: number
  onSessionProfileChange: (value: string) => void
  onSessionRoleChange: (value: string) => void
  onApplicationIdInputChange: (value: string) => void
  onCreateSession: (event: FormEvent) => void
  onAttachSession: (event: FormEvent) => void
  onResolveThread: () => void
  onLoadHistory: () => void
  onBroadcastPing: () => void
}

export function SessionControlPanel({
  sessionProfileId,
  sessionRole,
  applicationIdInput,
  applicationId,
  threadId,
  workflowId,
  traceId,
  connectedParticipantCount,
  onSessionProfileChange,
  onSessionRoleChange,
  onApplicationIdInputChange,
  onCreateSession,
  onAttachSession,
  onResolveThread,
  onLoadHistory,
  onBroadcastPing,
}: SessionControlPanelProps) {
  return (
    <article className="panel session-panel">
      <h2>Session Control</h2>
      <p className="panel-subtext">Create, attach, and inspect thread identity and run metadata.</p>

      <form className="session-form" onSubmit={onCreateSession}>
        <label htmlFor="sessionProfile">profile ID</label>
        <input
          id="sessionProfile"
          value={sessionProfileId}
          onChange={(event) => onSessionProfileChange(event.target.value)}
        />
        <label htmlFor="sessionRole">role</label>
        <input id="sessionRole" value={sessionRole} onChange={(event) => onSessionRoleChange(event.target.value)} />
        <button type="submit">Create Session</button>
      </form>

      <form className="session-form attach-form" onSubmit={onAttachSession}>
        <label htmlFor="applicationInput">attach application ID</label>
        <input
          id="applicationInput"
          value={applicationIdInput}
          onChange={(event) => onApplicationIdInputChange(event.target.value)}
          placeholder="app_xxx"
        />
        <button type="submit">Attach</button>
      </form>

      <div className="session-meta">
        <div>
          <span>application_id</span>
          <code>{applicationId || 'n/a'}</code>
        </div>
        <div>
          <span>thread_id</span>
          <code>{threadId ?? 'n/a'}</code>
        </div>
        <div>
          <span>workflow_id</span>
          <code>{workflowId ?? 'n/a'}</code>
        </div>
        <div>
          <span>langsmith_trace_id</span>
          <code>{traceId ?? 'n/a'}</code>
        </div>
      </div>

      <div className="button-row">
        <button type="button" onClick={onResolveThread} disabled={!applicationId}>
          Resolve Thread
        </button>
        <button type="button" onClick={onLoadHistory} disabled={!applicationId}>
          Load History
        </button>
        <button type="button" onClick={onBroadcastPing} disabled={connectedParticipantCount === 0}>
          Ping all sockets
        </button>
      </div>
    </article>
  )
}
