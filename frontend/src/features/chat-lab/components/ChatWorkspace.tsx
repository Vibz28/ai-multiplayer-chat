import type { CSSProperties } from 'react'

import { ChecklistPanel } from './ChecklistPanel'
import { ComposerPanel } from './ComposerPanel'
import { ConversationSidebar } from './ConversationSidebar'
import { TranscriptPanel } from './TranscriptPanel'
import type { ChatLabController } from '../hooks/useChatLabController'
import { profileHue, streamSummary } from '../utils/presentation'

type ChatWorkspaceProps = {
  controller: ChatLabController
  inviteStatus: string
  shareUrl: string
  onCopyShareUrl: () => Promise<void>
  onOpenShareUrl: () => void
  onOpenControlStudio: () => void
}

export function ChatWorkspace({
  controller,
  inviteStatus,
  shareUrl,
  onCopyShareUrl,
  onOpenShareUrl,
  onOpenControlStudio,
}: ChatWorkspaceProps) {
  const selectedSenderId = controller.selectedSender?.id ?? ''
  const hasMessages = controller.messages.length > 0
  const streamText = streamSummary(controller.streamState)

  return (
    <section className="chat-layout">
      <ConversationSidebar
        conversations={controller.conversations}
        activeApplicationId={controller.applicationId}
        applicationId={controller.applicationId}
        applicationIdInput={controller.applicationIdInput}
        inviteStatus={inviteStatus}
        shareUrl={shareUrl}
        onApplicationIdInputChange={controller.setApplicationIdInput}
        onAttachSession={controller.attachSession}
        onQuickStartSession={controller.quickStartSession}
        onOpenConversation={controller.openConversation}
        onCopyShareUrl={onCopyShareUrl}
        onOpenShareUrl={onOpenShareUrl}
      />

      <section className={hasMessages ? 'chat-stage panel active' : 'chat-stage panel idle'}>
        <div className="chat-stage-header">
          <div>
            <h2>Conversation</h2>
            <p>Focus on messaging. IDs, diagnostics, and controls stay tucked away.</p>
          </div>
          <div className="status-pills">
            <span data-state={controller.connectionSummary}>{controller.connectionSummary}</span>
            <span data-state={controller.streamState}>{streamText}</span>
            <span data-state={controller.isIncognito ? 'incognito' : 'standard'}>
              {controller.isIncognito ? 'incognito persona' : 'standard persona'}
            </span>
          </div>
        </div>

        <TranscriptPanel
          messages={controller.messages}
          expandedReasoning={controller.expandedReasoning}
          transcriptRef={controller.transcriptRef}
          onToggleReasoning={controller.toggleReasoning}
        />

        <div className={hasMessages ? 'composer-zone docked' : 'composer-zone hero'}>
          {!hasMessages && (
            <div className="hero-hint">
              <p>Send the first message to begin this thread.</p>
              <p>After that, the composer docks below and the transcript stays front-and-center.</p>
            </div>
          )}
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
        </div>
      </section>

      <aside className="right-rail">
        <ChecklistPanel items={controller.checklistItems} state={controller.checklistState} />

        <section className="panel people-panel">
          <div className="panel-heading compact">
            <h3>People in this chat</h3>
            <span>{controller.connectedParticipantIds.length} connected</span>
          </div>

          <div className="people-list">
            {controller.participants.map((participant) => (
              <article
                key={participant.id}
                className={participant.id === selectedSenderId ? 'person-card active' : 'person-card'}
                style={{ '--persona-hue': `${profileHue(participant.profileId)}deg` } as CSSProperties}
              >
                <button
                  type="button"
                  className="person-select"
                  onClick={() => controller.setSelectedSenderId(participant.id)}
                >
                  <span className="person-avatar">{participant.profileId.slice(0, 2).toUpperCase()}</span>
                  <span>
                    <strong>{participant.profileId}</strong>
                    <small>{participant.role}</small>
                  </span>
                </button>
                <span className="connection-state" data-state={participant.connectionState}>
                  {participant.connectionState}
                </span>
                <div className="person-actions">
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => controller.connectParticipant(participant.id)}
                    disabled={!controller.applicationId || participant.connectionState === 'connected'}
                  >
                    Connect
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => controller.disconnectParticipant(participant.id)}
                    disabled={participant.connectionState !== 'connected'}
                  >
                    Disconnect
                  </button>
                </div>
              </article>
            ))}
          </div>

          <div className="button-row compact wrap">
            <button type="button" className="ghost" onClick={controller.addParticipant}>
              Add profile
            </button>
            <button
              type="button"
              className="ghost"
              onClick={controller.connectAllParticipants}
              disabled={!controller.applicationId}
            >
              Connect everyone
            </button>
            <button type="button" className="ghost" onClick={controller.disconnectAllParticipants}>
              Disconnect all
            </button>
          </div>
        </section>

        <section className="session-snapshot panel">
          <h3>Session</h3>
          <p>Friendly overview with advanced IDs tucked away.</p>
          <div className="session-chip-row">
            <span>{controller.selectedSender?.profileId ?? 'no profile'}</span>
            <span>{controller.selectedSender?.role ?? 'member'}</span>
            <span>{controller.streamState}</span>
          </div>

          <details>
            <summary>Show advanced IDs and debug controls</summary>
            <ul>
              <li>application_id: {controller.applicationId || 'n/a'}</li>
              <li>thread_id: {controller.threadId ?? 'n/a'}</li>
              <li>workflow_id: {controller.workflowId ?? 'n/a'}</li>
              <li>trace_id: {controller.traceId ?? 'n/a'}</li>
            </ul>
            <div className="button-row compact wrap">
              <button type="button" className="ghost" onClick={controller.resolveThread} disabled={!controller.applicationId}>
                Resolve thread
              </button>
              <button type="button" className="ghost" onClick={controller.loadHistory} disabled={!controller.applicationId}>
                Load history
              </button>
              <button type="button" className="ghost" onClick={controller.broadcastPing}>
                Ping sockets
              </button>
            </div>
          </details>

          <div className="button-row compact wrap">
            <button type="button" className="ghost" onClick={() => void onCopyShareUrl()} disabled={!shareUrl}>
              Copy invite link
            </button>
            <button type="button" className="ghost" onClick={onOpenShareUrl} disabled={!shareUrl}>
              Open invite tab
            </button>
            <button type="button" className="ghost" onClick={onOpenControlStudio}>
              Open control studio
            </button>
          </div>
          {inviteStatus && <p className="hint-text">{inviteStatus}</p>}
        </section>
      </aside>
    </section>
  )
}
