import { useEffect, useRef, useState } from 'react'
import type { Artifact, ChatMessage, ChecklistItem, EventEnvelope, HistoryEntry, RosterParticipant, StreamState } from '../../types'

const backendHttpUrl = import.meta.env.VITE_BACKEND_HTTP_URL?.replace(/\/$/, '') ?? 'http://localhost:8000'
const backendWsUrl = import.meta.env.VITE_BACKEND_WS_URL?.replace(/\/$/, '') ?? 'ws://localhost:8000'
const ROOM_STORAGE_KEY = 'fieldwork.room.v1'
const NAME_STORAGE_KEY = 'fieldwork.name.v1'
const HARNESS_STORAGE_KEY = 'fieldwork.harness.v1'

export type HarnessName = 'Moss Cloud' | 'Codex' | 'Claude Code' | 'OpenCode' | 'Pi'
export type HarnessRoute = {
  available: boolean
  provider?: string
  model?: string | null
  reason?: string
}
type ConnectionState = 'joining' | 'online' | 'reconnecting' | 'offline'

type WorkerRoom = {
  applicationId: string
  inviteUrl: string
  profileName: string
  harness: HarnessName
  harnessRoutes: Partial<Record<HarnessName, HarnessRoute>>
  connectionState: ConnectionState
  streamState: StreamState
  messages: ChatMessage[]
  checklist: ChecklistItem[]
  artifacts: Artifact[]
  completedCount: number
  roster: RosterParticipant[]
  draft: string
  error: string
  isStarting: boolean
  setProfileName: (value: string) => void
  setHarness: (value: HarnessName) => void
  setDraft: (value: string) => void
  setError: (value: string) => void
  startRoom: () => Promise<void>
  startNewRoom: () => Promise<void>
  sendMessage: () => void
  downloadArtifact: (artifact: Artifact) => Promise<void>
}

function initialRoomId() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  if (params.get('room')) return params.get('room') as string
  try {
    const saved = JSON.parse(window.localStorage.getItem(ROOM_STORAGE_KEY) ?? '{}') as { id?: string }
    return saved.id ?? ''
  } catch {
    return ''
  }
}

function initialRoomToken() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  if (params.get('key')) return params.get('key') as string
  try {
    const saved = JSON.parse(window.localStorage.getItem(ROOM_STORAGE_KEY) ?? '{}') as { token?: string }
    return saved.token ?? ''
  } catch {
    return ''
  }
}

function historyMessage(entry: HistoryEntry, index: number): ChatMessage | null {
  if (entry.channel !== 'transcript' && entry.channel !== 'content') return null
  const kind = entry.role === 'assistant' ? 'assistant' : 'user'
  return {
    id: `history-${index}-${entry.created_at}`,
    kind,
    senderProfileId: kind === 'assistant' ? 'Moss' : entry.profile_id ?? 'Teammate',
    senderRole: entry.role,
    createdAt: entry.created_at,
    content: entry.content,
    reasoning: '',
    complete: true,
  }
}

function eventRoster(payload: Record<string, unknown>): RosterParticipant[] | null {
  if (!Array.isArray(payload.participants)) return null
  return payload.participants.filter((item): item is RosterParticipant => {
    if (!item || typeof item !== 'object') return false
    const candidate = item as Partial<RosterParticipant>
    return typeof candidate.profile_id === 'string' && typeof candidate.role === 'string'
  })
}

function mergeHydratedMessages(hydrated: ChatMessage[], live: ChatMessage[]) {
  const merged = [...hydrated]
  for (const message of live) {
    const duplicate = hydrated.some((candidate) => (
      candidate.kind === message.kind
      && candidate.senderProfileId === message.senderProfileId
      && candidate.content === message.content
      && Math.abs(new Date(candidate.createdAt).getTime() - new Date(message.createdAt).getTime()) < 5000
    ))
    if (!duplicate) merged.push(message)
  }
  return merged.sort((left, right) => Date.parse(left.createdAt) - Date.parse(right.createdAt))
}

function roomHeaders(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export function useWorkerRoom(): WorkerRoom {
  const [applicationId, setApplicationId] = useState(initialRoomId)
  const [roomToken, setRoomToken] = useState(initialRoomToken)
  const [profileName, setProfileNameState] = useState(() => window.localStorage.getItem(NAME_STORAGE_KEY) ?? 'You')
  const [harness, setHarnessState] = useState<HarnessName>(() => {
    const saved = window.localStorage.getItem(HARNESS_STORAGE_KEY)
    return saved === 'Codex' || saved === 'Claude Code' || saved === 'OpenCode' || saved === 'Pi' ? saved : 'Moss Cloud'
  })
  const [harnessRoutes, setHarnessRoutes] = useState<Partial<Record<HarnessName, HarnessRoute>>>({})
  const [connectionState, setConnectionState] = useState<ConnectionState>(applicationId ? 'joining' : 'offline')
  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [checklist, setChecklist] = useState<ChecklistItem[]>([])
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [roster, setRoster] = useState<RosterParticipant[]>([])
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [reconnectAttempt, setReconnectAttempt] = useState(0)
  const [roomValidated, setRoomValidated] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const assistantDraftRef = useRef<string | null>(null)
  const profileNameRef = useRef(profileName)

  const inviteUrl = applicationId && roomToken ? `${window.location.origin}${window.location.pathname}#room=${applicationId}&key=${roomToken}` : ''
  const completedCount = checklist.filter((item) => item.done).length

  useEffect(() => {
    profileNameRef.current = profileName
    window.localStorage.setItem(NAME_STORAGE_KEY, profileName)
  }, [profileName])

  useEffect(() => {
    window.localStorage.setItem(HARNESS_STORAGE_KEY, harness)
  }, [harness])

  useEffect(() => {
    if (!applicationId || !roomToken) return
    let active = true

    const hydrate = async () => {
      try {
        const headers = roomHeaders(roomToken)
        const sessionResponse = await fetch(`${backendHttpUrl}/v1/sessions/${applicationId}`, { headers })
        if (!active) return
        if ([401, 403, 404].includes(sessionResponse.status)) {
          window.localStorage.removeItem(ROOM_STORAGE_KEY)
          window.history.replaceState({}, '', window.location.pathname)
          setRoomValidated(false)
          setConnectionState('offline')
          setRoomToken('')
          setApplicationId('')
          setMessages([])
          setChecklist([])
          setArtifacts([])
          setRoster([])
          setHarnessRoutes({})
          assistantDraftRef.current = null
          setError('That room invite is no longer valid. Start a fresh room to continue.')
          return
        }
        if (!sessionResponse.ok) throw new Error('The worker service is unavailable right now.')
        await fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/thread`, { method: 'POST', headers })
        const [historyResponse, checklistResponse, artifactsResponse, routesResponse] = await Promise.all([
          fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/history?limit=300`, { headers }),
          fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/checklist`, { headers }),
          fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/artifacts`, { headers }),
          fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/model-routes`, { headers }),
        ])
        if (!active) return
        setRoomValidated(true)
        if (historyResponse.ok) {
          const history = await historyResponse.json() as { entries: HistoryEntry[] }
          const hydrated = history.entries.map(historyMessage).filter((message): message is ChatMessage => message !== null)
          setMessages((current) => mergeHydratedMessages(hydrated, current))
        }
        if (checklistResponse.ok) {
          const payload = await checklistResponse.json() as { items: ChecklistItem[] }
          setChecklist(payload.items)
        }
        if (artifactsResponse.ok) {
          const payload = await artifactsResponse.json() as { items: Artifact[] }
          setArtifacts(payload.items)
        }
        if (routesResponse.ok) {
          const payload = await routesResponse.json() as { routes?: Record<string, HarnessRoute> }
          const routes = payload.routes ?? {}
          const mappedRoutes: Partial<Record<HarnessName, HarnessRoute>> = {
            'Moss Cloud': routes.langgraph,
            Codex: routes.codex,
            'Claude Code': routes.claude_code,
            OpenCode: routes.opencode,
            Pi: routes.pi,
          }
          setHarnessRoutes(mappedRoutes)
          if (mappedRoutes[harness]?.available === false) {
            setHarnessState('Moss Cloud')
            setError(`${harness} needs a compatible platform provider grant. Switched to Moss Cloud.`)
          }
        }
      } catch (cause) {
        if (!active) return
        setError(cause instanceof Error ? cause.message : 'Unable to open this room.')
      }
    }

    void hydrate()
    return () => { active = false }
  }, [applicationId, harness, reconnectAttempt, roomToken])

  useEffect(() => {
    if (!applicationId || !roomToken || !roomValidated) return
    let active = true
    let reconnectTimer: number | undefined
    setConnectionState(reconnectAttempt > 0 ? 'reconnecting' : 'joining')

    const socket = new WebSocket(`${backendWsUrl}/ws/${applicationId}`, [`fieldwork.${roomToken}`])
    socketRef.current = socket
    socket.onopen = () => {
      if (!active) return
      setConnectionState('online')
      setError('')
      socket.send(JSON.stringify({ type: 'join', profile_id: profileNameRef.current || 'Guest', role: 'collaborator' }))
    }
    socket.onmessage = (incoming) => {
      if (!active) return
      try {
        const event = JSON.parse(String(incoming.data)) as EventEnvelope
        const nextRoster = eventRoster(event.payload)
        if (nextRoster) setRoster(nextRoster)

        if (event.type === 'user_message') {
          const content = typeof event.payload.content === 'string' ? event.payload.content : ''
          const sender = typeof event.payload.profile_id === 'string' ? event.payload.profile_id : 'Teammate'
          setMessages((current) => [...current, {
            id: `person-${event.timestamp}-${current.length}`,
            kind: 'user',
            senderProfileId: sender,
            senderRole: 'collaborator',
            createdAt: event.timestamp,
            content,
            reasoning: '',
            complete: true,
          }])
          return
        }

        if (event.type === 'status') {
          const message = event.payload.message
          if (message === 'queued_for_agent') setStreamState('queued')
          if (message === 'agent_run_started') setStreamState('generating')
          return
        }

        if (event.type === 'reasoning') {
          setStreamState('reasoning')
          return
        }

        if (event.type === 'content') {
          setStreamState('generating')
          const delta = typeof event.payload.delta === 'string' ? event.payload.delta : ''
          if (!assistantDraftRef.current) {
            assistantDraftRef.current = `moss-${event.timestamp}`
            setMessages((current) => [...current, {
              id: assistantDraftRef.current as string,
              kind: 'assistant',
              senderProfileId: 'Moss',
              senderRole: 'worker',
              createdAt: event.timestamp,
              content: delta,
              reasoning: '',
              complete: false,
            }])
          } else {
            const draftId = assistantDraftRef.current
            setMessages((current) => current.map((message) => message.id === draftId ? { ...message, content: `${message.content}${delta}` } : message))
          }
          return
        }

        if (event.type === 'checklist' && Array.isArray(event.payload.items)) {
          setChecklist(event.payload.items as ChecklistItem[])
          return
        }

        if (event.type === 'complete') {
          const draftId = assistantDraftRef.current
          if (draftId) setMessages((current) => current.map((message) => message.id === draftId ? { ...message, complete: true } : message))
          assistantDraftRef.current = null
          setStreamState('completed')
          const headers = roomHeaders(roomToken)
          void Promise.all([
            fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/history?limit=300`, { headers }),
            fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/checklist`, { headers }),
            fetch(`${backendHttpUrl}/v1/sessions/${applicationId}/artifacts`, { headers }),
          ]).then(async ([historyResponse, checklistResponse, artifactsResponse]) => {
            if (historyResponse.ok) {
              const history = await historyResponse.json() as { entries: HistoryEntry[] }
              const hydrated = history.entries.map(historyMessage).filter((message): message is ChatMessage => message !== null)
              setMessages((current) => mergeHydratedMessages(hydrated, current))
            }
            if (checklistResponse.ok) setChecklist(((await checklistResponse.json()) as { items: ChecklistItem[] }).items)
            if (artifactsResponse.ok) {
              const payload = await artifactsResponse.json() as { items: Artifact[] }
              setArtifacts(payload.items)
            }
          })
          return
        }

        if (event.type === 'error') {
          const draftId = assistantDraftRef.current
          if (draftId) setMessages((current) => current.map((message) => message.id === draftId ? { ...message, complete: true } : message))
          assistantDraftRef.current = null
          setStreamState('error')
          setError(typeof event.payload.message === 'string' ? event.payload.message : 'Moss ran into a problem.')
        }
      } catch {
        setError('The room received a message it could not understand.')
      }
    }
    socket.onerror = () => {
      if (active) setConnectionState('reconnecting')
    }
    socket.onclose = () => {
      if (!active) return
      const draftId = assistantDraftRef.current
      if (draftId) {
        setMessages((current) => current.map((message) => (
          message.id === draftId ? { ...message, complete: true } : message
        )))
      }
      assistantDraftRef.current = null
      setConnectionState('reconnecting')
      const delay = Math.min(1000 * 2 ** reconnectAttempt, 12_000)
      reconnectTimer = window.setTimeout(() => setReconnectAttempt((attempt) => attempt + 1), delay)
    }

    return () => {
      active = false
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket.close()
      if (socketRef.current === socket) socketRef.current = null
    }
  }, [applicationId, reconnectAttempt, roomToken, roomValidated])

  const setProfileName = (value: string) => {
    profileNameRef.current = value
    setProfileNameState(value)
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'join', profile_id: value || 'Guest', role: 'collaborator' }))
    }
  }
  const setHarness = (value: HarnessName) => setHarnessState(value)

  const startRoom = async () => {
    setIsStarting(true)
    setError('')
    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: profileName || 'You', role: 'collaborator' }),
      })
      if (!response.ok) throw new Error('The worker service is unavailable right now.')
      const payload = await response.json() as { application_id: string; room_token: string }
      await fetch(`${backendHttpUrl}/v1/sessions/${payload.application_id}/thread`, {
        method: 'POST',
        headers: roomHeaders(payload.room_token),
      })
      window.localStorage.setItem(ROOM_STORAGE_KEY, JSON.stringify({ id: payload.application_id, token: payload.room_token }))
      window.history.replaceState({}, '', `${window.location.pathname}#room=${payload.application_id}&key=${payload.room_token}`)
      setMessages([])
      setChecklist([])
      setArtifacts([])
      setRoster([])
      setHarnessRoutes({})
      assistantDraftRef.current = null
      setRoomValidated(false)
      setReconnectAttempt(0)
      setRoomToken(payload.room_token)
      setApplicationId(payload.application_id)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to prepare your room.')
    } finally {
      setIsStarting(false)
    }
  }

  const startNewRoom = async () => {
    socketRef.current?.close()
    window.localStorage.removeItem(ROOM_STORAGE_KEY)
    setApplicationId('')
    await startRoom()
  }

  const sendMessage = () => {
    const content = draft.trim()
    if (!content) return
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError('Still reconnecting. Your message is safe in the composer.')
      return
    }
    socket.send(JSON.stringify({
      type: 'user_message',
      content,
      profile_id: profileName || 'You',
      role: 'collaborator',
      include_ai: true,
      delivery_mode: 'thread',
      recipient_profile_ids: [],
      harness: harness === 'Moss Cloud' ? 'langgraph' : harness.toLowerCase().replace(' ', '_'),
      client_request_id: crypto.randomUUID(),
    }))
    setDraft('')
    setError('')
    setStreamState('queued')
  }

  const downloadArtifact = async (artifact: Artifact) => {
    if (!applicationId || !roomToken) return
    try {
      const response = await fetch(
        `${backendHttpUrl}/v1/sessions/${applicationId}/artifacts/${artifact.artifact_id}/content`,
        { headers: roomHeaders(roomToken) },
      )
      if (!response.ok) throw new Error('Unable to download this deliverable.')
      const url = URL.createObjectURL(await response.blob())
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = artifact.filename
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to download this deliverable.')
    }
  }

  return {
    applicationId,
    inviteUrl,
    profileName,
    harness,
    harnessRoutes,
    connectionState,
    streamState,
    messages,
    checklist,
    artifacts,
    completedCount,
    roster,
    draft,
    error,
    isStarting,
    setProfileName,
    setHarness,
    setDraft,
    setError,
    startRoom,
    startNewRoom,
    sendMessage,
    downloadArtifact,
  }
}
