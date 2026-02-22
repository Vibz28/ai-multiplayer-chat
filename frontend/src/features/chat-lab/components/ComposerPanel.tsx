import type { FormEvent } from 'react'

type SenderOption = {
  id: string
  label: string
}

type ComposerPanelProps = {
  mode?: 'focused' | 'full'
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
  mode = 'full',
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
  const focused = mode === 'focused'

  return (
    <article className={`composer-panel ${focused ? 'focused' : ''}`}>
      <h2>{focused ? 'Message Composer' : 'Composer'}</h2>
      <form className="composer-form" onSubmit={onSendMessage}>
        <div className="composer-grid">
          <label>
            persona
            <select value={selectedSenderId} onChange={(event) => onSelectedSenderChange(event.target.value)}>
              {senderOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="inline-check">
            <input
              checked={includeAi}
              onChange={(event) => onIncludeAiChange(event.target.checked)}
              type="checkbox"
            />
            include AI response
          </label>
        </div>

        <label>
          message
          <textarea
            value={messageInput}
            onChange={(event) => onMessageInputChange(event.target.value)}
            placeholder="Type a message. Press Send to stream response live."
          />
        </label>

        <details className="advanced-composer" open={!focused}>
          <summary>{focused ? 'Advanced delivery options' : 'Delivery options'}</summary>
          <div className="advanced-composer-body">
            <label>
              delivery mode
              <select
                value={deliveryMode}
                onChange={(event) => onDeliveryModeChange(event.target.value as 'thread' | 'direct')}
              >
                <option value="thread">group thread</option>
                <option value="direct">private/direct</option>
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
          </div>
        </details>

        <div className="button-row">
          <button type="submit" disabled={!selectedSenderId || !applicationId}>
            Send Message
          </button>
          <button type="button" onClick={onSendConcurrentAiBurst} disabled={!applicationId}>
            Burst Test
          </button>
        </div>
      </form>

      {errorMessage && <p className="error-text">{errorMessage}</p>}
    </article>
  )
}
