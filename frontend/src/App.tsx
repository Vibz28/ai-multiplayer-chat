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

  return (
    <main className="chat-dashboard">
      <header className="dashboard-header panel">
        <div>
          <p className="kicker">AI Multiplayer Chat Platform</p>
          <h1>Conversation Sandbox</h1>
          <p className="subtitle">
            A chat-first workspace for testing live streaming, typing states, persona swaps, and
            collaborative thread behavior without drowning in admin controls.
          </p>
        </div>
        <div className="header-actions">
          <button type="button" onClick={() => void controller.quickStartSession()}>
            {controller.applicationId ? 'Session Ready' : 'Start Chat Session'}
          </button>
          <button
            type="button"
            className={controller.isIncognito ? 'ghost active' : 'ghost'}
            onClick={() => void controller.toggleIncognitoMode()}
          >
            {controller.isIncognito ? 'Exit Incognito' : 'Incognito Session'}
          </button>
          <button type="button" className="ghost" onClick={() => setOpsVisible((current) => !current)}>
            {opsVisible ? 'Hide Ops Console' : 'Show Ops Console'}
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

      <section className="quick-guide panel">
        <div>
          <h2>Quick Start</h2>
          <ol>
            <li>Press <strong>Start Chat Session</strong> to create/resolve a thread quickly.</li>
            <li>Choose a persona chip and connect it (or connect all for concurrency tests).</li>
            <li>Send prompts to watch live output/reasoning streams and checklist updates.</li>
          </ol>
        </div>
        <div className="guide-metrics">
          <div>
            <span>application_id</span>
            <code>{controller.applicationId || 'n/a'}</code>
          </div>
          <div>
            <span>thread_id</span>
            <code>{controller.threadId ?? 'n/a'}</code>
          </div>
          <div>
            <span>persona</span>
            <code>{selectedProfileLabel}</code>
          </div>
          <div>
            <span>stream state</span>
            <code>{controller.streamState}</code>
          </div>
        </div>
      </section>

      <section className={`dashboard-body ${opsVisible ? 'with-ops' : ''}`}>
        <section className="chat-stage panel">
          <div className="status-pills">
            <span data-state={controller.connectionSummary}>connections: {controller.connectionSummary}</span>
            <span data-state={controller.streamState}>stream: {controller.streamState}</span>
            <span data-state={controller.isIncognito ? 'incognito' : 'standard'}>
              {controller.isIncognito ? 'mode: incognito' : 'mode: standard'}
            </span>
          </div>

          <section className="identity-swapper">
            <div className="panel-heading">
              <h2>Persona Switcher</h2>
              <p>Swap local user viewpoint instantly across connected participants.</p>
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
            <div className="button-row">
              <button
                type="button"
                onClick={() => selectedSenderId && controller.connectParticipant(selectedSenderId)}
                disabled={!controller.applicationId || !selectedSenderId}
              >
                Connect Selected
              </button>
              <button type="button" onClick={controller.connectAllParticipants} disabled={!controller.applicationId}>
                Connect All
              </button>
              <button type="button" className="ghost" onClick={controller.disconnectAllParticipants}>
                Disconnect All
              </button>
            </div>
          </section>

          <ChecklistPanel items={controller.checklistItems} state={controller.checklistState} />

          <TranscriptPanel
            messages={controller.messages}
            expandedReasoning={controller.expandedReasoning}
            transcriptRef={controller.transcriptRef}
            onToggleReasoning={controller.toggleReasoning}
          />

          <div className={`typing-indicator state-${controller.streamState}`}>
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
            <p>{streamText}</p>
          </div>

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

        {opsVisible && (
          <aside className="ops-drawer panel">
            <div className="panel-heading">
              <h2>Ops Console</h2>
              <p>Advanced controls for debug, trace, and multi-user orchestration tests.</p>
            </div>

            <details open>
              <summary>Session and Thread</summary>
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
            </details>

            <details>
              <summary>Participants</summary>
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
            </details>

            <details>
              <summary>WebSocket Trace</summary>
              <EventTracePanel events={controller.events} eventLogRef={controller.eventLogRef} />
            </details>
          </aside>
        )}
      </section>
    </main>
  )
}

export default App
