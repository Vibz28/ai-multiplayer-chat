import type { FormEvent } from 'react'

type SenderOption = {
  id: string
  label: string
}

type ComposerPanelProps = {
  applicationId: string
  selectedSenderId: string
  senderOptions: SenderOption[]
  deliveryMode: 'thread' | 'direct'
  recipientCsv: string
  includeAi: boolean
  messageInput: string
  availableRecipientProfiles: string[]
  errorMessage: string
  onSendMessage: (event: FormEvent) => void
  onSendConcurrentAiBurst: () => void
  onSelectedSenderChange: (senderId: string) => void
  onDeliveryModeChange: (mode: 'thread' | 'direct') => void
  onRecipientCsvChange: (value: string) => void
  onIncludeAiChange: (value: boolean) => void
  onMessageInputChange: (value: string) => void
}

export function ComposerPanel({
  applicationId,
  selectedSenderId,
  senderOptions,
  deliveryMode,
  recipientCsv,
  includeAi,
  messageInput,
  availableRecipientProfiles,
  errorMessage,
  onSendMessage,
  onSendConcurrentAiBurst,
  onSelectedSenderChange,
  onDeliveryModeChange,
  onRecipientCsvChange,
  onIncludeAiChange,
  onMessageInputChange,
}: ComposerPanelProps) {
  return (
    <article className="panel composer-panel">
      <h2>Composer</h2>
      <form className="composer-form" onSubmit={onSendMessage}>
        <label>
          sender
          <select value={selectedSenderId} onChange={(event) => onSelectedSenderChange(event.target.value)}>
            {senderOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          delivery mode
          <select
            value={deliveryMode}
            onChange={(event) => onDeliveryModeChange(event.target.value as 'thread' | 'direct')}
          >
            <option value="thread">thread broadcast</option>
            <option value="direct">direct profiles</option>
          </select>
        </label>

        <label>
          recipients (comma-separated)
          <input
            disabled={deliveryMode !== 'direct'}
            value={recipientCsv}
            onChange={(event) => onRecipientCsvChange(event.target.value)}
            placeholder={availableRecipientProfiles.join(', ') || 'profile IDs'}
          />
        </label>

        <label className="inline-check">
          <input checked={includeAi} onChange={(event) => onIncludeAiChange(event.target.checked)} type="checkbox" />
          include AI response
        </label>

        <label>
          message
          <textarea
            value={messageInput}
            onChange={(event) => onMessageInputChange(event.target.value)}
            placeholder="Type a group/direct message or AI request"
          />
        </label>

        <div className="button-row">
          <button type="submit" disabled={!selectedSenderId || !applicationId}>
            Send
          </button>
          <button type="button" onClick={onSendConcurrentAiBurst} disabled={!applicationId}>
            Concurrent AI Burst
          </button>
        </div>
      </form>

      {errorMessage && <p className="error-text">{errorMessage}</p>}
    </article>
  )
}
