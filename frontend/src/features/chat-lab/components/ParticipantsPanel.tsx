import type { Participant, RosterParticipant } from '../../../types'

type ParticipantsPanelProps = {
  applicationId: string
  participants: Participant[]
  roster: RosterParticipant[]
  onUpdateParticipantField: (participantId: string, field: 'profileId' | 'role', value: string) => void
  onConnectParticipant: (participantId: string) => void
  onDisconnectParticipant: (participantId: string) => void
  onRemoveParticipant: (participantId: string) => void
  onAddParticipant: () => void
}

export function ParticipantsPanel({
  applicationId,
  participants,
  roster,
  onUpdateParticipantField,
  onConnectParticipant,
  onDisconnectParticipant,
  onRemoveParticipant,
  onAddParticipant,
}: ParticipantsPanelProps) {
  return (
    <article className="panel participants-panel">
      <h2>Participant Routing</h2>
      <p>
        Each participant keeps an independent WebSocket to the same application/thread for
        multiplayer and queueing tests.
      </p>

      <div className="participant-list">
        {participants.map((participant) => (
          <div key={participant.id} className="participant-card">
            <input
              aria-label="participant profile"
              value={participant.profileId}
              onChange={(event) =>
                onUpdateParticipantField(participant.id, 'profileId', event.target.value)
              }
            />
            <input
              aria-label="participant role"
              value={participant.role}
              onChange={(event) => onUpdateParticipantField(participant.id, 'role', event.target.value)}
            />
            <code data-state={participant.connectionState}>{participant.connectionState}</code>
            <div className="participant-actions">
              <button
                type="button"
                onClick={() => onConnectParticipant(participant.id)}
                disabled={!applicationId || participant.connectionState === 'connected'}
              >
                connect
              </button>
              <button
                type="button"
                onClick={() => onDisconnectParticipant(participant.id)}
                disabled={participant.connectionState !== 'connected'}
              >
                disconnect
              </button>
              <button type="button" className="ghost" onClick={() => onRemoveParticipant(participant.id)}>
                remove
              </button>
            </div>
          </div>
        ))}
      </div>

      <button type="button" className="ghost" onClick={onAddParticipant}>
        Add Participant
      </button>

      <h3>Connected Roster</h3>
      <ul className="roster-list">
        {roster.length === 0 && <li>no connected participants reported yet</li>}
        {roster.map((participant) => (
          <li key={`${participant.profile_id}-${participant.connected_at}`}>
            <strong>{participant.profile_id}</strong>
            <span>{participant.role}</span>
          </li>
        ))}
      </ul>
    </article>
  )
}
