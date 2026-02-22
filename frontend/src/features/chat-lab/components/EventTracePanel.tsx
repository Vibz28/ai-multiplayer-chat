import type { RefObject } from 'react'

import type { EventEnvelope } from '../../../types'

type EventTracePanelProps = {
  events: EventEnvelope[]
  eventLogRef: RefObject<HTMLDivElement | null>
}

export function EventTracePanel({ events, eventLogRef }: EventTracePanelProps) {
  return (
    <article className="panel events-panel">
      <h2>WebSocket Event Trace</h2>
      <div className="event-log" ref={eventLogRef}>
        {events.length === 0 && <p className="empty">No websocket events yet.</p>}
        {events.map((event) => (
          <article key={`${event.timestamp}-${event.type}`} className="event-card">
            <header>
              <strong>{event.type}</strong>
              <span>{event.stream_state ?? 'n/a'}</span>
            </header>
            <code>{event.timestamp}</code>
            <pre>{JSON.stringify(event.payload, null, 2)}</pre>
          </article>
        ))}
      </div>
    </article>
  )
}
