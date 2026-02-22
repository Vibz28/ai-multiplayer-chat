import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'

import { MarkdownMermaid } from './components/MarkdownMermaid'
import './App.css'
import type {
  ChatMessage,
  EventEnvelope,
  Participant,
  RosterParticipant,
  SessionHistoryResponse,
  SessionResponse,
  StreamState,
  ThreadResponse,
} from './types'

const backendHttpUrl =
  import.meta.env.VITE_BACKEND_HTTP_URL?.replace(/\/$/, '') ?? 'http://localhost:8000'
const backendWsUrl = import.meta.env.VITE_BACKEND_WS_URL?.replace(/\/$/, '') ?? 'ws://localhost:8000'

const MAX_EVENT_LOG = 600
const THEME_STORAGE_KEY = 'chatlab-theme'

type ThemeMode = 'light' | 'dark'

function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((entry): entry is string => typeof entry === 'string')
}

function parseRoster(payload: Record<string, unknown>): RosterParticipant[] {
  const rawParticipants = payload.participants
  if (!Array.isArray(rawParticipants)) {
    return []
  }

  return rawParticipants
    .map((entry) => {
      if (!entry || typeof entry !== 'object') {
        return null
      }
      const typed = entry as Record<string, unknown>
      return {
        profile_id: asString(typed.profile_id, 'unknown'),
        role: asString(typed.role, 'member'),
        connected_at: asString(typed.connected_at, new Date().toISOString()),
      }
    })
    .filter((entry): entry is RosterParticipant => entry !== null)
}

function parseRunIdentity(payload: Record<string, unknown>): { runId: string; traceId: string } {
  const nestedRun = payload.run
  if (nestedRun && typeof nestedRun === 'object') {
    const runRecord = nestedRun as Record<string, unknown>
    const nestedRunId = asString(runRecord.run_id, '')
    const nestedTraceId = asString(runRecord.trace_id, '')
    if (nestedRunId || nestedTraceId) {
      return { runId: nestedRunId, traceId: nestedTraceId }
    }
  }
  return {
    runId: asString(payload.run_id, ''),
    traceId: asString(payload.trace_id, ''),
  }
}

function initialTheme(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light'
  }
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') {
    return saved
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function historyToMessages(history: SessionHistoryResponse): ChatMessage[] {
  const messages: ChatMessage[] = []
  const assistantByRun = new Map<string, string>()

  for (const entry of history.entries) {
    if (entry.channel === 'transcript') {
      const message: ChatMessage = {
        id: newId('history'),
        kind: entry.role === 'assistant' ? 'assistant' : 'user',
        senderProfileId: entry.profile_id ?? entry.role,
        senderRole: entry.role,
        createdAt: entry.created_at,
        content: entry.content,
        reasoning: '',
        includeAi: entry.role !== 'assistant',
        deliveryMode: 'thread',
        recipientProfileIds: [],
        runId: entry.run_id ?? undefined,
        traceId: entry.trace_id ?? undefined,
        complete: true,
      }
      messages.push(message)
      if (entry.role === 'assistant' && entry.run_id) {
        assistantByRun.set(entry.run_id, message.id)
      }
      continue
    }

    if (entry.channel === 'reasoning' && entry.run_id) {
      const targetId = assistantByRun.get(entry.run_id)
      if (!targetId) {
        continue
      }
      const target = messages.find((message) => message.id === targetId)
      if (target) {
        target.reasoning = `${target.reasoning}${entry.content}`
      }
      continue
    }

    if (entry.channel === 'error') {
      messages.push({
        id: newId('history-error'),
        kind: 'system',
        senderProfileId: 'system',
        senderRole: 'system',
        createdAt: entry.created_at,
        content: entry.content,
        reasoning: '',
        complete: true,
      })
    }
  }

  return messages
}

function App() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(initialTheme)

  const [sessionProfileId, setSessionProfileId] = useState('host-user')
  const [sessionRole, setSessionRole] = useState('member')
  const [applicationIdInput, setApplicationIdInput] = useState('')

  const [applicationId, setApplicationId] = useState('')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [traceId, setTraceId] = useState<string | null>(null)

  const [participants, setParticipants] = useState<Participant[]>([
    {
      id: newId('participant'),
      profileId: 'host-user',
      role: 'member',
      connectionState: 'disconnected',
    },
    {
      id: newId('participant'),
      profileId: 'guest-user',
      role: 'member',
      connectionState: 'disconnected',
    },
  ])
  const [selectedSenderId, setSelectedSenderId] = useState<string | null>(null)
  const [roster, setRoster] = useState<RosterParticipant[]>([])

  const [messageInput, setMessageInput] = useState('')
  const [deliveryMode, setDeliveryMode] = useState<'thread' | 'direct'>('thread')
  const [recipientCsv, setRecipientCsv] = useState('')
  const [includeAi, setIncludeAi] = useState(true)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [events, setEvents] = useState<EventEnvelope[]>([])
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({})

  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [errorMessage, setErrorMessage] = useState('')

  const socketsRef = useRef<Map<string, WebSocket>>(new Map())
  const seenEventKeysRef = useRef<Set<string>>(new Set())
  const activeAssistantByRunRef = useRef<Map<string, string>>(new Map())
  const activeAssistantFallbackIdRef = useRef<string | null>(null)

  const transcriptRef = useRef<HTMLDivElement | null>(null)
  const eventLogRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode])

  useEffect(() => {
    if (participants.length === 0) {
      setSelectedSenderId(null)
      return
    }
    const hasCurrent = participants.some((participant) => participant.id === selectedSenderId)
    if (!hasCurrent) {
      setSelectedSenderId(participants[0]?.id ?? null)
    }
  }, [participants, selectedSenderId])

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight })
  }, [messages])

  useEffect(() => {
    eventLogRef.current?.scrollTo({ top: eventLogRef.current.scrollHeight })
  }, [events])

  useEffect(() => {
    const sockets = socketsRef.current
    return () => {
      for (const socket of sockets.values()) {
        socket.close()
      }
      sockets.clear()
    }
  }, [])

  const connectedParticipantIds = useMemo(
    () =>
      participants
        .filter((participant) => participant.connectionState === 'connected')
        .map((participant) => participant.id),
    [participants],
  )

  const senderOptions = useMemo(
    () =>
      participants.map((participant) => ({
        id: participant.id,
        label: `${participant.profileId} (${participant.role})`,
      })),
    [participants],
  )

  const selectedSender = useMemo(
    () => participants.find((participant) => participant.id === selectedSenderId) ?? participants[0] ?? null,
    [participants, selectedSenderId],
  )

  const availableRecipientProfiles = useMemo(() => {
    const profileIds = new Set<string>()
    for (const participant of participants) {
      profileIds.add(participant.profileId)
    }
    for (const participant of roster) {
      profileIds.add(participant.profile_id)
    }
    if (selectedSender) {
      profileIds.delete(selectedSender.profileId)
    }
    return [...profileIds].sort()
  }, [participants, roster, selectedSender])

  const connectionSummary = useMemo(() => {
    const connected = participants.filter((participant) => participant.connectionState === 'connected').length
    if (connected === 0) {
      return 'disconnected'
    }
    if (connected < participants.length) {
      return 'partial'
    }
    return 'connected'
  }, [participants])

  const appendEvent = (event: EventEnvelope) => {
    setEvents((current) => {
      const next = [...current, event]
      return next.length > MAX_EVENT_LOG ? next.slice(next.length - MAX_EVENT_LOG) : next
    })
  }

  const appendSystemMessage = (content: string) => {
    setMessages((current) => [
      ...current,
      {
        id: newId('system'),
        kind: 'system',
        senderProfileId: 'system',
        senderRole: 'system',
        createdAt: new Date().toISOString(),
        content,
        reasoning: '',
        complete: true,
      },
    ])
  }

  const ensureAssistantDraft = (options: { initiatedBy: string; runId?: string; traceId?: string }) => {
    const runId = options.runId ?? ''
    if (runId) {
      const existingByRun = activeAssistantByRunRef.current.get(runId)
      if (existingByRun) {
        return existingByRun
      }
    }

    const fallback = activeAssistantFallbackIdRef.current
    if (fallback) {
      if (runId) {
        activeAssistantByRunRef.current.set(runId, fallback)
      }
      return fallback
    }

    const draftId = newId('assistant')
    activeAssistantFallbackIdRef.current = draftId
    if (runId) {
      activeAssistantByRunRef.current.set(runId, draftId)
    }

    setMessages((current) => [
      ...current,
      {
        id: draftId,
        kind: 'assistant',
        senderProfileId: options.initiatedBy || 'assistant',
        senderRole: 'assistant',
        createdAt: new Date().toISOString(),
        content: '',
        reasoning: '',
        runId: runId || undefined,
        traceId: options.traceId || undefined,
        complete: false,
      },
    ])

    return draftId
  }

  const completeAssistantDraft = (runId: string, traceId: string) => {
    const byRunId = runId ? activeAssistantByRunRef.current.get(runId) : null
    const targetId = byRunId ?? activeAssistantFallbackIdRef.current
    if (!targetId) {
      return
    }

    setMessages((current) =>
      current.map((message) =>
        message.id === targetId
          ? {
              ...message,
              runId: runId || message.runId,
              traceId: traceId || message.traceId,
              complete: true,
            }
          : message,
      ),
    )

    if (runId) {
      activeAssistantByRunRef.current.delete(runId)
    }
    if (activeAssistantFallbackIdRef.current === targetId) {
      activeAssistantFallbackIdRef.current = null
    }
  }

  const resetSessionRuntime = () => {
    setMessages([])
    setEvents([])
    setRoster([])
    setStreamState('idle')
    setExpandedReasoning({})
    seenEventKeysRef.current.clear()
    activeAssistantByRunRef.current.clear()
    activeAssistantFallbackIdRef.current = null
  }

  const clearSockets = () => {
    for (const socket of socketsRef.current.values()) {
      socket.close()
    }
    socketsRef.current.clear()
    setParticipants((current) =>
      current.map((participant) => ({
        ...participant,
        connectionState: 'disconnected',
      })),
    )
  }

  const createSession = async (event: FormEvent) => {
    event.preventDefault()
    setErrorMessage('')

    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: sessionProfileId || null,
          role: sessionRole || 'member',
        }),
      })
      if (!response.ok) {
        throw new Error(`Session creation failed with status ${response.status}`)
      }
      const payload = (await response.json()) as SessionResponse
      setApplicationId(payload.application_id)
      setApplicationIdInput(payload.application_id)
      setThreadId(payload.langgraph_thread_id)
      setWorkflowId(payload.workflow_id)
      setTraceId(payload.langsmith_trace_id)
      clearSockets()
      resetSessionRuntime()
      appendSystemMessage(`Session created for ${payload.application_id}`)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown session creation error')
    }
  }

  const attachSession = async (event: FormEvent) => {
    event.preventDefault()
    setErrorMessage('')
    if (!applicationIdInput.trim()) {
      setErrorMessage('Enter an existing application ID')
      return
    }

    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions/${applicationIdInput.trim()}`)
      if (!response.ok) {
        throw new Error(`Session lookup failed with status ${response.status}`)
      }
      const payload = (await response.json()) as SessionResponse
      setApplicationId(payload.application_id)
      setThreadId(payload.langgraph_thread_id)
      setWorkflowId(payload.workflow_id)
      setTraceId(payload.langsmith_trace_id)
      clearSockets()
      resetSessionRuntime()
      appendSystemMessage(`Attached to session ${payload.application_id}`)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown session attach error')
    }
  }

  const resolveThread = async () => {
    if (!applicationId) {
      setErrorMessage('Create or attach to an application first')
      return
    }
    setErrorMessage('')

    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/thread`, {
        method: 'POST',
      })
      if (!response.ok) {
        throw new Error(`Thread resolution failed with status ${response.status}`)
      }
      const payload = (await response.json()) as ThreadResponse
      setThreadId(payload.langgraph_thread_id)
      setWorkflowId(payload.workflow_id)
      setTraceId(payload.langsmith_trace_id)
      appendSystemMessage(`Thread ready: ${payload.langgraph_thread_id}`)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown thread resolution error')
    }
  }

  const loadHistory = async () => {
    if (!applicationId) {
      setErrorMessage('No active application ID')
      return
    }
    setErrorMessage('')
    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/history?limit=300`)
      if (!response.ok) {
        throw new Error(`History fetch failed with status ${response.status}`)
      }
      const payload = (await response.json()) as SessionHistoryResponse
      setThreadId(payload.langgraph_thread_id)
      setWorkflowId(payload.workflow_id)
      setTraceId(payload.langsmith_trace_id)
      setMessages(historyToMessages(payload))
      activeAssistantByRunRef.current.clear()
      activeAssistantFallbackIdRef.current = null
      appendSystemMessage(`Loaded ${payload.count} history entries`)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown history fetch error')
    }
  }

  const upsertParticipant = (participantId: string, patch: Partial<Participant>) => {
    setParticipants((current) =>
      current.map((participant) =>
        participant.id === participantId ? { ...participant, ...patch } : participant,
      ),
    )
  }

  const connectParticipant = (participantId: string) => {
    if (!applicationId) {
      setErrorMessage('Create or attach an application before connecting sockets')
      return
    }
    const participant = participants.find((candidate) => candidate.id === participantId)
    if (!participant) {
      return
    }

    const existingSocket = socketsRef.current.get(participantId)
    if (existingSocket && existingSocket.readyState === WebSocket.OPEN) {
      return
    }

    upsertParticipant(participantId, { connectionState: 'connecting' })
    const socket = new WebSocket(`${backendWsUrl}/ws/${applicationId}`)
    socketsRef.current.set(participantId, socket)

    socket.onopen = () => {
      upsertParticipant(participantId, { connectionState: 'connected' })
      socket.send(
        JSON.stringify({
          type: 'join',
          profile_id: participant.profileId,
          role: participant.role,
        }),
      )
    }

    socket.onmessage = (incoming) => {
      try {
        const parsed = JSON.parse(String(incoming.data)) as EventEnvelope
        handleSocketEvent(parsed, participantId)
      } catch {
        setErrorMessage('Received non-JSON websocket payload')
      }
    }

    socket.onerror = () => {
      upsertParticipant(participantId, { connectionState: 'error' })
      setErrorMessage(`WebSocket error for participant ${participant.profileId}`)
      setStreamState('error')
    }

    socket.onclose = () => {
      socketsRef.current.delete(participantId)
      upsertParticipant(participantId, { connectionState: 'disconnected' })
    }
  }

  const disconnectParticipant = (participantId: string) => {
    const participant = participants.find((candidate) => candidate.id === participantId)
    const socket = socketsRef.current.get(participantId)
    if (participant && socket && socket.readyState === WebSocket.OPEN) {
      socket.send(
        JSON.stringify({
          type: 'leave',
          profile_id: participant.profileId,
          role: participant.role,
        }),
      )
    }
    socket?.close()
    socketsRef.current.delete(participantId)
    upsertParticipant(participantId, { connectionState: 'disconnected' })
  }

  const broadcastPing = () => {
    for (const [participantId, socket] of socketsRef.current.entries()) {
      if (socket.readyState !== WebSocket.OPEN) {
        continue
      }
      socket.send(JSON.stringify({ type: 'ping' }))
      upsertParticipant(participantId, { connectionState: 'connected' })
    }
  }

  const sendMessage = (event: FormEvent) => {
    event.preventDefault()
    setErrorMessage('')
    if (!selectedSender) {
      setErrorMessage('Choose a sender profile before sending')
      return
    }

    const content = messageInput.trim()
    if (!content) {
      return
    }

    const socket = socketsRef.current.get(selectedSender.id)
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setErrorMessage(`Sender ${selectedSender.profileId} is not connected`)
      return
    }

    const recipients = recipientCsv
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0 && item !== selectedSender.profileId)

    socket.send(
      JSON.stringify({
        type: 'user_message',
        content,
        profile_id: selectedSender.profileId,
        role: selectedSender.role,
        include_ai: includeAi,
        delivery_mode: deliveryMode,
        recipient_profile_ids: recipients,
      }),
    )

    if (includeAi) {
      setStreamState('generating')
    }
    setMessageInput('')
  }

  const sendConcurrentAiBurst = () => {
    const content = messageInput.trim()
    if (!content) {
      return
    }

    const connected = participants.filter((participant) => {
      const socket = socketsRef.current.get(participant.id)
      return socket?.readyState === WebSocket.OPEN
    })

    if (connected.length < 2) {
      setErrorMessage('Connect at least two participants for concurrency burst test')
      return
    }

    for (const participant of connected) {
      const socket = socketsRef.current.get(participant.id)
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        continue
      }
      socket.send(
        JSON.stringify({
          type: 'user_message',
          content: `${content} [sender=${participant.profileId}]`,
          profile_id: participant.profileId,
          role: participant.role,
          include_ai: true,
          delivery_mode: 'thread',
          recipient_profile_ids: [],
        }),
      )
    }

    setStreamState('queued')
    setMessageInput('')
  }

  const handleSocketEvent = (event: EventEnvelope, sourceParticipantId: string) => {
    const dedupeKey = `${event.timestamp}|${event.type}|${event.thread_id ?? '-'}|${JSON.stringify(event.payload)}`
    if (seenEventKeysRef.current.has(dedupeKey)) {
      return
    }
    seenEventKeysRef.current.add(dedupeKey)
    if (seenEventKeysRef.current.size > 6000) {
      seenEventKeysRef.current.clear()
    }

    appendEvent(event)
    if (event.thread_id) {
      setThreadId(event.thread_id)
    }

    const payload = event.payload
    const { runId, traceId: parsedTraceId } = parseRunIdentity(payload)
    if (runId) {
      setWorkflowId(runId)
    }
    if (parsedTraceId) {
      setTraceId(parsedTraceId)
    }

    const rosterFromEvent = parseRoster(payload)
    if (rosterFromEvent.length > 0) {
      setRoster(rosterFromEvent)
    }

    if (event.type === 'participant_join' || event.type === 'participant_leave') {
      return
    }

    if (event.type === 'user_message') {
      setMessages((current) => [
        ...current,
        {
          id: newId('user'),
          kind: 'user',
          senderProfileId: asString(payload.profile_id, 'unknown'),
          senderRole: asString(payload.role, 'member'),
          createdAt: event.timestamp,
          content: asString(payload.content),
          reasoning: '',
          includeAi: payload.include_ai !== false,
          deliveryMode: asString(payload.delivery_mode, 'thread') === 'direct' ? 'direct' : 'thread',
          recipientProfileIds: asStringArray(payload.recipient_profile_ids),
          complete: true,
        },
      ])
      if (payload.include_ai === false) {
        setStreamState('idle')
      }
      return
    }

    if (event.type === 'status') {
      const message = asString(payload.message)
      if (message === 'queued_for_agent') {
        setStreamState('queued')
        return
      }
      if (message === 'agent_run_started') {
        setStreamState('generating')
        const initiatedBy = asString(payload.profile_id, 'assistant')
        ensureAssistantDraft({ initiatedBy, runId, traceId: parsedTraceId })
        return
      }
      if (message === 'pong') {
        upsertParticipant(sourceParticipantId, { connectionState: 'connected' })
      }
      return
    }

    if (event.type === 'reasoning') {
      setStreamState('reasoning')
      const initiatedBy = asString(payload.initiated_by_profile_id, 'assistant')
      const targetId = ensureAssistantDraft({ initiatedBy, runId, traceId: parsedTraceId })
      const delta = asString(payload.delta)
      setMessages((current) =>
        current.map((message) =>
          message.id === targetId
            ? {
                ...message,
                runId: runId || message.runId,
                traceId: parsedTraceId || message.traceId,
                reasoning: `${message.reasoning}${delta}`,
              }
            : message,
        ),
      )
      return
    }

    if (event.type === 'content') {
      setStreamState('generating')
      const initiatedBy = asString(payload.initiated_by_profile_id, 'assistant')
      const targetId = ensureAssistantDraft({ initiatedBy, runId, traceId: parsedTraceId })
      const delta = asString(payload.delta)
      setMessages((current) =>
        current.map((message) =>
          message.id === targetId
            ? {
                ...message,
                runId: runId || message.runId,
                traceId: parsedTraceId || message.traceId,
                content: `${message.content}${delta}`,
              }
            : message,
        ),
      )
      return
    }

    if (event.type === 'complete') {
      setStreamState('completed')
      completeAssistantDraft(runId, parsedTraceId)
      return
    }

    if (event.type === 'error') {
      setStreamState('error')
      activeAssistantByRunRef.current.clear()
      activeAssistantFallbackIdRef.current = null
      appendSystemMessage(asString(payload.message, 'Unknown stream error'))
    }
  }

  const addParticipant = () => {
    const created: Participant = {
      id: newId('participant'),
      profileId: `user-${participants.length + 1}`,
      role: 'member',
      connectionState: 'disconnected',
    }
    setParticipants((current) => [...current, created])
  }

  const removeParticipant = (participantId: string) => {
    disconnectParticipant(participantId)
    setParticipants((current) => current.filter((participant) => participant.id !== participantId))
  }

  const updateParticipantField = (
    participantId: string,
    field: 'profileId' | 'role',
    value: string,
  ) => {
    setParticipants((current) =>
      current.map((participant) =>
        participant.id === participantId ? { ...participant, [field]: value } : participant,
      ),
    )
  }

  const toggleReasoning = (messageId: string) => {
    setExpandedReasoning((current) => ({
      ...current,
      [messageId]: !current[messageId],
    }))
  }

  return (
    <main className="app-shell">
      <header className="app-header panel">
        <div>
          <p className="kicker">Phase 3 · Multiplayer Frontend</p>
          <h1>Multiplayer WebSocket Chat Lab</h1>
          <p className="subtitle">
            Validate user-to-user, user-to-group, user-to-AI, and multi-user AI concurrency on a
            shared thread with live status, reasoning, and content streams.
          </p>
        </div>
        <div className="header-controls">
          <div className="status-pills" aria-label="connection and stream state">
            <span data-state={connectionSummary}>connections: {connectionSummary}</span>
            <span data-state={streamState}>stream: {streamState}</span>
          </div>
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setThemeMode((current) => (current === 'light' ? 'dark' : 'light'))}
            aria-label="Toggle light and dark theme"
          >
            {themeMode === 'light' ? 'Dark mode' : 'Light mode'}
          </button>
        </div>
      </header>

      <section className="workspace-grid">
        <article className="panel session-panel">
          <h2>Session Control</h2>

          <form className="session-form" onSubmit={createSession}>
            <label htmlFor="sessionProfile">session profile</label>
            <input
              id="sessionProfile"
              value={sessionProfileId}
              onChange={(event) => setSessionProfileId(event.target.value)}
            />
            <label htmlFor="sessionRole">session role</label>
            <input
              id="sessionRole"
              value={sessionRole}
              onChange={(event) => setSessionRole(event.target.value)}
            />
            <button type="submit">Create Session</button>
          </form>

          <form className="session-form attach-form" onSubmit={attachSession}>
            <label htmlFor="applicationInput">attach application_id</label>
            <input
              id="applicationInput"
              value={applicationIdInput}
              onChange={(event) => setApplicationIdInput(event.target.value)}
              placeholder="app_xxx"
            />
            <button type="submit">Attach</button>
          </form>

          <div className="session-meta">
            <div>
              <span>application_id</span>
              <code>{applicationId || 'n/a'}</code>
            </div>
            <div>
              <span>thread_id</span>
              <code>{threadId ?? 'n/a'}</code>
            </div>
            <div>
              <span>workflow_id</span>
              <code>{workflowId ?? 'n/a'}</code>
            </div>
            <div>
              <span>langsmith_trace_id</span>
              <code>{traceId ?? 'n/a'}</code>
            </div>
          </div>

          <div className="button-row">
            <button type="button" onClick={resolveThread} disabled={!applicationId}>
              Resolve Thread
            </button>
            <button type="button" onClick={loadHistory} disabled={!applicationId}>
              Load History
            </button>
            <button type="button" onClick={broadcastPing} disabled={connectedParticipantIds.length === 0}>
              Ping All
            </button>
          </div>
        </article>

        <article className="panel participants-panel">
          <h2>Participants</h2>
          <p>
            Each participant holds an independent WebSocket to the same application/thread for
            multiplayer and queuing tests.
          </p>

          <div className="participant-list">
            {participants.map((participant) => (
              <div key={participant.id} className="participant-card">
                <input
                  aria-label="participant profile"
                  value={participant.profileId}
                  onChange={(event) =>
                    updateParticipantField(participant.id, 'profileId', event.target.value)
                  }
                />
                <input
                  aria-label="participant role"
                  value={participant.role}
                  onChange={(event) => updateParticipantField(participant.id, 'role', event.target.value)}
                />
                <code data-state={participant.connectionState}>{participant.connectionState}</code>
                <div className="participant-actions">
                  <button
                    type="button"
                    onClick={() => connectParticipant(participant.id)}
                    disabled={!applicationId || participant.connectionState === 'connected'}
                  >
                    connect
                  </button>
                  <button
                    type="button"
                    onClick={() => disconnectParticipant(participant.id)}
                    disabled={participant.connectionState !== 'connected'}
                  >
                    disconnect
                  </button>
                  <button type="button" className="ghost" onClick={() => removeParticipant(participant.id)}>
                    remove
                  </button>
                </div>
              </div>
            ))}
          </div>

          <button type="button" className="ghost" onClick={addParticipant}>
            Add Participant
          </button>

          <h3>Server Roster</h3>
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
      </section>

      <section className="workspace-grid chat-grid">
        <article className="panel composer-panel">
          <h2>Composer</h2>
          <form className="composer-form" onSubmit={sendMessage}>
            <label>
              sender
              <select
                value={selectedSender?.id ?? ''}
                onChange={(event) => setSelectedSenderId(event.target.value)}
              >
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
                onChange={(event) => setDeliveryMode(event.target.value as 'thread' | 'direct')}
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
                onChange={(event) => setRecipientCsv(event.target.value)}
                placeholder={availableRecipientProfiles.join(', ') || 'profile IDs'}
              />
            </label>

            <label className="inline-check">
              <input
                checked={includeAi}
                onChange={(event) => setIncludeAi(event.target.checked)}
                type="checkbox"
              />
              include AI response
            </label>

            <label>
              message
              <textarea
                value={messageInput}
                onChange={(event) => setMessageInput(event.target.value)}
                placeholder="Type a group/direct message or AI request"
              />
            </label>

            <div className="button-row">
              <button type="submit" disabled={!selectedSender || !applicationId}>
                Send
              </button>
              <button type="button" onClick={sendConcurrentAiBurst} disabled={!applicationId}>
                Concurrent AI Burst
              </button>
            </div>
          </form>

          {errorMessage && <p className="error-text">{errorMessage}</p>}
        </article>

        <article className="panel transcript-panel">
          <h2>Transcript</h2>
          <div className="message-list" ref={transcriptRef}>
            {messages.length === 0 && <p className="empty">No chat messages yet.</p>}
            {messages.map((message) => (
              <article key={message.id} className={`message-card ${message.kind}`}>
                <header>
                  <div>
                    <strong>{message.senderProfileId}</strong>
                    <span>{message.senderRole}</span>
                  </div>
                  <time>{new Date(message.createdAt).toLocaleTimeString()}</time>
                </header>

                {message.kind === 'assistant' ? (
                  <MarkdownMermaid markdown={message.content || '_waiting for content stream..._'} />
                ) : (
                  <pre>{message.content}</pre>
                )}

                {message.kind !== 'assistant' && message.deliveryMode && (
                  <p className="message-meta">
                    mode={message.deliveryMode}
                    {message.recipientProfileIds && message.recipientProfileIds.length > 0
                      ? ` targets=${message.recipientProfileIds.join(', ')}`
                      : ''}
                    {message.includeAi ? ' +ai' : ' no-ai'}
                  </p>
                )}

                {message.kind === 'assistant' && (
                  <div className="assistant-meta">
                    <button type="button" className="ghost" onClick={() => toggleReasoning(message.id)}>
                      {expandedReasoning[message.id] ? 'Hide reasoning' : 'Show reasoning'}
                    </button>
                    <span>{message.complete ? 'complete' : 'streaming'}</span>
                  </div>
                )}

                {message.kind === 'assistant' && expandedReasoning[message.id] && (
                  <pre className="reasoning-box">
                    {message.reasoning || '(waiting for reasoning stream or tool calls)'}
                  </pre>
                )}
              </article>
            ))}
          </div>
        </article>

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
      </section>
    </main>
  )
}

export default App
