import { useMemo } from 'react'

import { EventTracePanel } from './EventTracePanel'
import { ParticipantsPanel } from './ParticipantsPanel'
import { SessionControlPanel } from './SessionControlPanel'
import type { ChatLabController } from '../hooks/useChatLabController'
import { distributionFromSummary, shortId, summarizeEvents } from '../utils/presentation'

type ControlStudioProps = {
  controller: ChatLabController
}

export function ControlStudio({ controller }: ControlStudioProps) {
  const eventSummary = useMemo(() => summarizeEvents(controller.events), [controller.events])
  const eventDistribution = useMemo(
    () => distributionFromSummary(eventSummary),
    [eventSummary],
  )

  return (
    <section className="control-studio panel">
      <header className="studio-header">
        <div>
          <h2>Control Studio</h2>
          <p>Admin-focused diagnostics, routing controls, and websocket event observability.</p>
        </div>
        <div className="metric-grid">
          <article>
            <span>Total events</span>
            <strong>{eventSummary.total}</strong>
          </article>
          <article>
            <span>User messages</span>
            <strong>{eventSummary.userMessages}</strong>
          </article>
          <article>
            <span>AI content</span>
            <strong>{eventSummary.contentChunks}</strong>
          </article>
          <article>
            <span>Checklist</span>
            <strong>{eventSummary.checklistEvents}</strong>
          </article>
          <article>
            <span>Errors</span>
            <strong>{eventSummary.errors}</strong>
          </article>
        </div>
      </header>

      <section className="panel stream-mix-panel">
        <div className="panel-heading compact">
          <h3>Live event distribution</h3>
          <span>application: {shortId(controller.applicationId)}</span>
        </div>
        <ul className="stream-mix-list">
          {eventDistribution.map((item) => (
            <li key={item.key}>
              <span>{item.label}</span>
              <div className="stream-mix-track" role="presentation">
                <div className="stream-mix-bar" style={{ width: `${Math.max(item.ratio, 3)}%` }} />
              </div>
              <strong>{item.count}</strong>
            </li>
          ))}
        </ul>
      </section>

      <div className="studio-layout">
        <SessionControlPanel
          sessionProfileId={controller.sessionProfileId}
          sessionRole={controller.sessionRole}
          applicationIdInput={controller.applicationIdInput}
          applicationId={controller.applicationId}
          threadId={controller.threadId}
          workflowId={controller.workflowId}
          traceId={controller.traceId}
          connectedParticipantCount={controller.connectedParticipantIds.length}
          onSessionProfileChange={controller.setSessionProfileId}
          onSessionRoleChange={controller.setSessionRole}
          onApplicationIdInputChange={controller.setApplicationIdInput}
          onCreateSession={controller.createSession}
          onAttachSession={controller.attachSession}
          onResolveThread={controller.resolveThread}
          onLoadHistory={controller.loadHistory}
          onBroadcastPing={controller.broadcastPing}
        />

        <ParticipantsPanel
          applicationId={controller.applicationId}
          participants={controller.participants}
          roster={controller.roster}
          onUpdateParticipantField={controller.updateParticipantField}
          onConnectParticipant={controller.connectParticipant}
          onDisconnectParticipant={controller.disconnectParticipant}
          onRemoveParticipant={controller.removeParticipant}
          onAddParticipant={controller.addParticipant}
        />

        <EventTracePanel events={controller.events} eventLogRef={controller.eventLogRef} />
      </div>
    </section>
  )
}
