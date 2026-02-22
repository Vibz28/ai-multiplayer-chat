import { useEffect, useState } from 'react'

import './App.css'
import { ComposerPanel } from './features/chat-lab/components/ComposerPanel'
import { EventTracePanel } from './features/chat-lab/components/EventTracePanel'
import { HeaderBar } from './features/chat-lab/components/HeaderBar'
import { ParticipantsPanel } from './features/chat-lab/components/ParticipantsPanel'
import { SessionControlPanel } from './features/chat-lab/components/SessionControlPanel'
import { TranscriptPanel } from './features/chat-lab/components/TranscriptPanel'
import { useChatLabController } from './features/chat-lab/hooks/useChatLabController'
import { initialTheme, THEME_STORAGE_KEY } from './features/chat-lab/utils/chatLabUtils'

function App() {
  const [themeMode, setThemeMode] = useState(initialTheme)
  const controller = useChatLabController()

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode])

  return (
    <main className="app-shell">
      <HeaderBar
        connectionSummary={controller.connectionSummary}
        streamState={controller.streamState}
        themeMode={themeMode}
        onToggleTheme={() => setThemeMode((current) => (current === 'light' ? 'dark' : 'light'))}
      />

      <section className="workspace-grid">
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
      </section>

      <section className="workspace-grid chat-grid">
        <ComposerPanel
          applicationId={controller.applicationId}
          selectedSenderId={controller.selectedSender?.id ?? ''}
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

        <TranscriptPanel
          messages={controller.messages}
          expandedReasoning={controller.expandedReasoning}
          transcriptRef={controller.transcriptRef}
          onToggleReasoning={controller.toggleReasoning}
        />

        <EventTracePanel events={controller.events} eventLogRef={controller.eventLogRef} />
      </section>
    </main>
  )
}

export default App
