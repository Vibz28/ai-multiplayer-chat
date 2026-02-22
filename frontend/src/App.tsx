import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'

import './App.css'
import { ComposerPanel } from './features/chat-lab/components/ComposerPanel'
import { EventTracePanel } from './features/chat-lab/components/EventTracePanel'
import { ParticipantsPanel } from './features/chat-lab/components/ParticipantsPanel'
import { SessionControlPanel } from './features/chat-lab/components/SessionControlPanel'
import { TranscriptPanel } from './features/chat-lab/components/TranscriptPanel'
import { ChecklistPanel } from './features/chat-lab/components/ChecklistPanel'
import { useChatLabController } from './features/chat-lab/hooks/useChatLabController'
import { initialTheme, THEME_STORAGE_KEY, type ThemeMode } from './features/chat-lab/utils/chatLabUtils'

function profileHue(profileId: string): number {
  let hash = 0
  for (let i = 0; i < profileId.length; i += 1) {
    hash = (hash * 31 + profileId.charCodeAt(i)) % 360
  }
  return hash
}

function streamSummary(streamState: string): string {
  if (streamState === 'generating') {
    return 'Assistant is generating live output'
  }
  if (streamState === 'reasoning') {
    return 'Agent is reasoning and calling tools'
  }
  if (streamState === 'queued') {
    return 'Request queued for processing'
  }
  if (streamState === 'completed') {
    return 'Run completed'
  }
  if (streamState === 'error') {
    return 'Run ended with an error'
  }
  return 'Idle and ready'
}

function App() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(initialTheme)
  const [opsVisible, setOpsVisible] = useState(false)
  const controller = useChatLabController()

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode])

  const selectedProfileLabel = useMemo(() => {
    if (!controller.selectedSender) {
      return 'none'
    }
    return `${controller.selectedSender.profileId} (${controller.selectedSender.role})`
  }, [controller.selectedSender])

  const streamText = useMemo(() => streamSummary(controller.streamState), [controller.streamState])

  const selectedSenderId = controller.selectedSender?.id ?? ''
  const connectedCount = controller.connectedParticipantIds.length

  return (
    <main className="chat-app">
      <header className="topbar panel">
        <div className="brand-block">
          <p className="kicker">Multiplayer AI Workspace</p>
          <h1>Collaborative AI Chat</h1>
          <p className="subtitle">
            Bring multiple personas into one conversation, invite AI when needed, and track shared
            progress through a live checklist.
          </p>
        </div>
        <div className="topbar-actions">
          <button type="button" onClick={() => void controller.quickStartSession()}>
            {controller.applicationId ? 'Session Active' : 'Start Chat Session'}
          </button>
          <button
            type="button"
            className={controller.isIncognito ? 'ghost active' : 'ghost'}
            onClick={() => void controller.toggleIncognitoMode()}
          >
            {controller.isIncognito ? 'Incognito On' : 'Incognito Off'}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setThemeMode((current) => (current === 'light' ? 'dark' : 'light'))}
            aria-label="Toggle light and dark theme"
          >
            {themeMode === 'light' ? 'Dark mode' : 'Light mode'}
          </button>
        </div>
      </header>

      <section className="main-grid">
        <section className="conversation-shell panel">
          <div className="conversation-status">
            <span className="status-pill" data-state={controller.connectionSummary}>
              {connectedCount} connected
            </span>
            <span className="status-pill" data-state={controller.streamState}>
              {streamText}
            </span>
            <span className="status-pill" data-state={controller.isIncognito ? 'incognito' : 'standard'}>
              {controller.isIncognito ? 'Incognito' : 'Shared mode'}
            </span>
          </div>

          <section className="people-strip" aria-label="People in chat">
            <div className="people-strip-head">
              <h2>People in this chat</h2>
              <p>Choose who you are speaking as.</p>
            </div>
            <div className="persona-chips">
              {controller.participants.map((participant) => (
                <button
                  type="button"
                  key={participant.id}
                  className={participant.id === selectedSenderId ? 'persona active' : 'persona'}
                  style={{ '--persona-hue': `${profileHue(participant.profileId)}deg` } as CSSProperties}
                  onClick={() => controller.setSelectedSenderId(participant.id)}
                >
                  <strong>{participant.profileId}</strong>
                  <span>{participant.connectionState}</span>
                </button>
              ))}
            </div>
            <div className="button-row compact">
              <button
                type="button"
                onClick={() => selectedSenderId && controller.connectParticipant(selectedSenderId)}
                disabled={!controller.applicationId || !selectedSenderId}
              >
                Connect selected
              </button>
              <button type="button" className="ghost" onClick={controller.connectAllParticipants} disabled={!controller.applicationId}>
                Connect everyone
              </button>
              <button type="button" className="ghost" onClick={controller.disconnectAllParticipants}>
                Disconnect all
              </button>
            </div>
          </section>

          <TranscriptPanel
            messages={controller.messages}
            expandedReasoning={controller.expandedReasoning}
            transcriptRef={controller.transcriptRef}
            onToggleReasoning={controller.toggleReasoning}
          />

          <ComposerPanel
            mode="focused"
            applicationId={controller.applicationId}
            selectedSenderId={selectedSenderId}
            senderOptions={controller.senderOptions}
            deliveryMode={controller.deliveryMode}
            recipientCsv={controller.recipientCsv}
            includeAi={controller.includeAi}
            messageInput={controller.messageInput}
            availableRecipientProfiles={controller.availableRecipientProfiles}
            errorMessage={controller.errorMessage}
            onSendMessage={controller.sendMessage}
            onSendConcurrentAiBurst={controller.sendConcurrentAiBurst}
            onSelectedSenderChange={controller.setSelectedSenderId}
            onDeliveryModeChange={controller.setDeliveryMode}
            onRecipientCsvChange={controller.setRecipientCsv}
            onIncludeAiChange={controller.setIncludeAi}
            onMessageInputChange={controller.setMessageInput}
          />
        </section>

        <aside className="supporting-shell">
          <ChecklistPanel items={controller.checklistItems} state={controller.checklistState} />

          <section className="session-card panel">
            <div className="panel-heading">
              <h2>Session</h2>
              <p>Friendly overview with advanced IDs tucked away.</p>
            </div>
            <div className="session-badges">
              <span>{selectedProfileLabel}</span>
              <span>{controller.connectionSummary}</span>
              <span>{controller.streamState}</span>
            </div>
            <details>
              <summary>Show advanced IDs and debug controls</summary>
              <dl className="technical-meta">
                <div>
                  <dt>application_id</dt>
                  <dd>{controller.applicationId || 'n/a'}</dd>
                </div>
                <div>
                  <dt>thread_id</dt>
                  <dd>{controller.threadId ?? 'n/a'}</dd>
                </div>
                <div>
                  <dt>workflow_id</dt>
                  <dd>{controller.workflowId ?? 'n/a'}</dd>
                </div>
                <div>
                  <dt>trace_id</dt>
                  <dd>{controller.traceId ?? 'n/a'}</dd>
                </div>
              </dl>
              <div className="button-row compact">
                <button type="button" onClick={() => void controller.resolveThread()} disabled={!controller.applicationId}>
                  Resolve thread
                </button>
                <button type="button" className="ghost" onClick={() => void controller.loadHistory()} disabled={!controller.applicationId}>
                  Reload history
                </button>
                <button type="button" className="ghost" onClick={() => void controller.refreshChecklist()} disabled={!controller.applicationId}>
                  Refresh checklist
                </button>
              </div>
            </details>
          </section>

          <section className="ops-entry panel">
            <div className="panel-heading">
              <h2>Need Deep Diagnostics?</h2>
              <p>Open the ops console only when you need low-level WebSocket and API controls.</p>
            </div>
            <button type="button" className="ghost" onClick={() => setOpsVisible((current) => !current)}>
              {opsVisible ? 'Hide Ops Console' : 'Open Ops Console'}
            </button>
          </section>
        </aside>
      </section>

      {opsVisible && (
        <section className="ops-console panel">
          <div className="panel-heading">
            <h2>Ops Console</h2>
            <p>Advanced controls for thread wiring, diagnostics, participant sockets, and trace review.</p>
          </div>
          <div className="ops-grid">
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
      )}
    </main>
  )
}

export default App
