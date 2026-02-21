import { useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type ConnectionState = 'disconnected' | 'connecting' | 'connected'
type StreamState = 'idle' | 'generating' | 'reasoning' | 'completed' | 'error'

type SessionResponse = {
  application_id: string
  profile_id: string | null
  langgraph_thread_id: string | null
  created_at: string
  updated_at: string
}

type EventEnvelope = {
  type: string
  application_id: string
  thread_id: string | null
  stream_state: string | null
  timestamp: string
  payload: Record<string, unknown>
}

const backendHttpUrl =
  import.meta.env.VITE_BACKEND_HTTP_URL?.replace(/\/$/, '') ?? 'http://localhost:8000'
const backendWsUrl =
  import.meta.env.VITE_BACKEND_WS_URL?.replace(/\/$/, '') ?? 'ws://localhost:8000'

function App() {
  const [profileId, setProfileId] = useState('local-user-a')
  const [applicationId, setApplicationId] = useState('')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [events, setEvents] = useState<EventEnvelope[]>([])
  const [messageInput, setMessageInput] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const socketRef = useRef<WebSocket | null>(null)

  const canConnect = useMemo(
    () => applicationId.length > 0 && connectionState === 'disconnected',
    [applicationId, connectionState],
  )

  const appendEvent = (event: EventEnvelope) => {
    setEvents((current) => [...current, event])
    if (event.thread_id) {
      setThreadId(event.thread_id)
    }
    if (event.stream_state === 'generating') {
      setStreamState('generating')
    } else if (event.stream_state === 'reasoning') {
      setStreamState('reasoning')
    } else if (event.stream_state === 'completed') {
      setStreamState('completed')
    } else if (event.type === 'error') {
      setStreamState('error')
    }
  }

  const createSession = async (event: FormEvent) => {
    event.preventDefault()
    setErrorMessage('')
    setStreamState('idle')

    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ profile_id: profileId || null }),
      })

      if (!response.ok) {
        throw new Error(`Session creation failed with status ${response.status}`)
      }

      const payload = (await response.json()) as SessionResponse
      setApplicationId(payload.application_id)
      setThreadId(payload.langgraph_thread_id)
      setEvents([])
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown session creation error')
    }
  }

  const connectSocket = () => {
    if (!applicationId) {
      setErrorMessage('Create a session before connecting to WebSocket')
      return
    }

    setConnectionState('connecting')
    setErrorMessage('')

    const socket = new WebSocket(`${backendWsUrl}/ws/${applicationId}`)
    socketRef.current = socket

    socket.onopen = () => {
      setConnectionState('connected')
    }

    socket.onmessage = (incoming) => {
      try {
        const parsed = JSON.parse(incoming.data as string) as EventEnvelope
        appendEvent(parsed)
      } catch {
        setErrorMessage('Received non-JSON event payload from backend')
      }
    }

    socket.onerror = () => {
      setErrorMessage('WebSocket error encountered')
      setStreamState('error')
    }

    socket.onclose = () => {
      setConnectionState('disconnected')
    }
  }

  const disconnectSocket = () => {
    socketRef.current?.close()
    socketRef.current = null
    setConnectionState('disconnected')
  }

  const sendPing = () => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: 'ping' }))
    }
  }

  const sendMessage = (event: FormEvent) => {
    event.preventDefault()
    if (!messageInput.trim()) {
      return
    }
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      setErrorMessage('WebSocket is not connected')
      return
    }

    setStreamState('generating')
    socketRef.current.send(
      JSON.stringify({
        type: 'user_message',
        content: messageInput,
      }),
    )
    setMessageInput('')
  }

  return (
    <main className="app-shell">
      <section className="panel">
        <h1>AI Multiplayer Chat Foundation Console</h1>
        <p>
          Phase 1 validation UI for session creation, WebSocket relay checks, and event channel
          visibility.
        </p>

        <form className="inline-form" onSubmit={createSession}>
          <label htmlFor="profileId">Profile ID</label>
          <input
            id="profileId"
            value={profileId}
            onChange={(next) => setProfileId(next.target.value)}
            placeholder="local-user-a"
          />
          <button type="submit">Create Session</button>
        </form>

        <div className="meta-grid">
          <div>
            <span>Application ID</span>
            <code>{applicationId || 'not created'}</code>
          </div>
          <div>
            <span>Thread ID</span>
            <code>{threadId ?? 'not assigned'}</code>
          </div>
          <div>
            <span>Connection</span>
            <code>{connectionState}</code>
          </div>
          <div>
            <span>Stream State</span>
            <code>{streamState}</code>
          </div>
        </div>

        <div className="button-row">
          <button disabled={!canConnect} onClick={connectSocket} type="button">
            Connect
          </button>
          <button
            disabled={connectionState !== 'connected'}
            onClick={disconnectSocket}
            type="button"
          >
            Disconnect
          </button>
          <button disabled={connectionState !== 'connected'} onClick={sendPing} type="button">
            Ping
          </button>
        </div>

        <form className="inline-form" onSubmit={sendMessage}>
          <label htmlFor="messageInput">User Message</label>
          <input
            id="messageInput"
            value={messageInput}
            onChange={(next) => setMessageInput(next.target.value)}
            placeholder="Send a foundation test message"
          />
          <button disabled={connectionState !== 'connected'} type="submit">
            Send
          </button>
        </form>

        {errorMessage && <p className="error-text">{errorMessage}</p>}
      </section>

      <section className="panel">
        <h2>Event Log</h2>
        <div className="event-log">
          {events.length === 0 && <p>No events received yet.</p>}
          {events.map((event, index) => (
            <article key={`${event.timestamp}-${index}`} className="event-card">
              <header>
                <strong>{event.type}</strong>
                <span>{event.stream_state ?? 'n/a'}</span>
              </header>
              <code>{event.timestamp}</code>
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            </article>
          ))}
        </div>
      </section>
    </main>
  )
}

export default App
