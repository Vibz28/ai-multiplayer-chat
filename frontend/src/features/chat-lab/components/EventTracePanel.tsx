import type { RefObject } from 'react'

import type { EventEnvelope } from '../../../types'

type EventTracePanelProps = {
  events: EventEnvelope[]
  eventLogRef: RefObject<HTMLDivElement | null>
}

export function EventTracePanel({ events, eventLogRef }: EventTracePanelProps) {
  const countsByType = events.reduce<Record<string, number>>((acc, event) => {
    acc[event.type] = (acc[event.type] ?? 0) + 1
    return acc
  }, {})

  return (
    <article className="panel events-panel">
      <h2>Live Event Timeline</h2>
      <div className="event-summary-chips">
        <span>total: {events.length}</span>
        <span>user: {countsByType.user_message ?? 0}</span>
        <span>content: {countsByType.content ?? 0}</span>
        <span>checklist: {countsByType.checklist ?? 0}</span>
        <span>errors: {countsByType.error ?? 0}</span>
      </div>
      <div className="event-log" ref={eventLogRef}>
        {events.length === 0 && <p className="empty">No websocket events yet.</p>}
        {events.map((event) => (
          <article key={`${event.timestamp}-${event.type}`} className="event-card">
            <header>
              <strong>{event.type}</strong>
              <span>{event.stream_state ?? 'n/a'}</span>
            </header>
            <code>{event.timestamp}</code>
            <details>
              <summary>Payload</summary>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </details>
          </article>
        ))}
      </div>
    </article>
  )
}
