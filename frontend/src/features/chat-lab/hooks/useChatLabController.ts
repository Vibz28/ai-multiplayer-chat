import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, RefObject } from 'react'

import type {
  ChatMessage,
  ChecklistItem,
  ConversationSummary,
  EventEnvelope,
  Participant,
  RosterParticipant,
  SessionChecklistResponse,
  SessionHistoryResponse,
  SessionResponse,
  StreamState,
  ThreadResponse,
} from '../../../types'
import {
  asString,
  asStringArray,
  historyToMessages,
  newId,
  parseRoster,
  parseRunIdentity,
} from '../utils/chatLabUtils'

const backendHttpUrl =
  import.meta.env.VITE_BACKEND_HTTP_URL?.replace(/\/$/, '') ?? 'http://localhost:8000'
const backendWsUrl = import.meta.env.VITE_BACKEND_WS_URL?.replace(/\/$/, '') ?? 'ws://localhost:8000'

const MAX_EVENT_LOG = 600
const MAX_RECENT_CONVERSATIONS = 40
const CONVERSATION_STORAGE_KEY = 'chatlab.recent_conversations.v1'

type DeliveryMode = 'thread' | 'direct'

type SenderOption = {
  id: string
  label: string
}

export type ChatLabController = {
  sessionProfileId: string
  sessionRole: string
  applicationIdInput: string
  applicationId: string
  threadId: string | null
  workflowId: string | null
  traceId: string | null
  participants: Participant[]
  roster: RosterParticipant[]
  selectedSenderId: string | null
  senderOptions: SenderOption[]
  selectedSender: Participant | null
  connectedParticipantIds: string[]
  connectionSummary: 'disconnected' | 'partial' | 'connected'
  messageInput: string
  deliveryMode: DeliveryMode
  recipientCsv: string
  includeAi: boolean
  availableRecipientProfiles: string[]
  messages: ChatMessage[]
  events: EventEnvelope[]
  expandedReasoning: Record<string, boolean>
  streamState: StreamState
  errorMessage: string
  checklistItems: ChecklistItem[]
  checklistState: 'idle' | 'loading' | 'error'
  isIncognito: boolean
  conversations: ConversationSummary[]
  transcriptRef: RefObject<HTMLDivElement | null>
  eventLogRef: RefObject<HTMLDivElement | null>
  setSessionProfileId: (value: string) => void
  setSessionRole: (value: string) => void
  setApplicationIdInput: (value: string) => void
  setSelectedSenderId: (senderId: string) => void
  setDeliveryMode: (mode: DeliveryMode) => void
  setRecipientCsv: (value: string) => void
  setIncludeAi: (value: boolean) => void
  setMessageInput: (value: string) => void
  createSession: (event: FormEvent) => Promise<void>
  attachSession: (event: FormEvent) => Promise<void>
  openConversation: (targetApplicationId: string) => Promise<void>
  quickStartSession: () => Promise<void>
  resolveThread: () => Promise<void>
  loadHistory: () => Promise<void>
  refreshChecklist: () => Promise<void>
  toggleIncognitoMode: () => Promise<void>
  connectParticipant: (participantId: string) => void
  connectAllParticipants: () => void
  disconnectAllParticipants: () => void
  disconnectParticipant: (participantId: string) => void
  addParticipant: () => void
  removeParticipant: (participantId: string) => void
  updateParticipantField: (participantId: string, field: 'profileId' | 'role', value: string) => void
  broadcastPing: () => void
  sendMessage: (event: FormEvent) => void
  sendConcurrentAiBurst: () => void
  toggleReasoning: (messageId: string) => void
}

function summarizeText(value: string, maxChars = 90): string {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (!normalized) {
    return ''
  }
  return normalized.length > maxChars ? `${normalized.slice(0, maxChars - 1)}…` : normalized
}

function titleFromUserPrompt(prompt: string): string {
  const summarized = summarizeText(prompt, 52)
  return summarized || 'New conversation'
}

function safeLoadConversations(): ConversationSummary[] {
  try {
    const raw = window.localStorage.getItem(CONVERSATION_STORAGE_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter((item): item is ConversationSummary => {
      if (!item || typeof item !== 'object') {
        return false
      }
      return typeof item.applicationId === 'string' && item.applicationId.length > 0
    })
  } catch {
    return []
  }
}

export function useChatLabController(): ChatLabController {
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
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>('thread')
  const [recipientCsv, setRecipientCsv] = useState('')
  const [includeAi, setIncludeAi] = useState(true)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [events, setEvents] = useState<EventEnvelope[]>([])
  const [expandedReasoning, setExpandedReasoning] = useState<Record<string, boolean>>({})

  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [checklistItems, setChecklistItems] = useState<ChecklistItem[]>([])
  const [checklistState, setChecklistState] = useState<'idle' | 'loading' | 'error'>('idle')
  const [isIncognito, setIsIncognito] = useState(false)
  const [conversations, setConversations] = useState<ConversationSummary[]>(() =>
    safeLoadConversations(),
  )

  const socketsRef = useRef<Map<string, WebSocket>>(new Map())
  const seenEventKeysRef = useRef<Set<string>>(new Set())
  const activeAssistantByRunRef = useRef<Map<string, string>>(new Map())
  const activeAssistantFallbackIdRef = useRef<string | null>(null)
  const assistantPreviewByRunRef = useRef<Map<string, string>>(new Map())
  const urlAttachHandledRef = useRef(false)

  const transcriptRef = useRef<HTMLDivElement | null>(null)
  const eventLogRef = useRef<HTMLDivElement | null>(null)

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

  useEffect(() => {
    window.localStorage.setItem(CONVERSATION_STORAGE_KEY, JSON.stringify(conversations))
  }, [conversations])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (applicationId) {
      url.searchParams.set('app', applicationId)
    } else {
      url.searchParams.delete('app')
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
  }, [applicationId])

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

  const upsertConversation = (targetApplicationId: string, patch: Partial<ConversationSummary>) => {
    const now = new Date().toISOString()
    setConversations((current) => {
      const existing = current.find((entry) => entry.applicationId === targetApplicationId)
      const existingTitle = existing?.title ?? 'New conversation'
      const incomingTitle = patch.title
      const resolvedTitle =
        existing && existingTitle !== 'New conversation' && incomingTitle
          ? existingTitle
          : incomingTitle ?? existingTitle
      const next: ConversationSummary = {
        applicationId: targetApplicationId,
        title: resolvedTitle,
        summary: patch.summary ?? existing?.summary ?? 'No AI summary yet.',
        lastUpdated: patch.lastUpdated ?? now,
        threadId: patch.threadId ?? existing?.threadId ?? null,
        workflowId: patch.workflowId ?? existing?.workflowId ?? null,
        traceId: patch.traceId ?? existing?.traceId ?? null,
        activeProfileId: patch.activeProfileId ?? existing?.activeProfileId ?? null,
        isIncognito: patch.isIncognito ?? existing?.isIncognito ?? false,
      }
      const rest = current.filter((entry) => entry.applicationId !== targetApplicationId)
      return [next, ...rest].slice(0, MAX_RECENT_CONVERSATIONS)
    })
  }

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

  const completeAssistantDraft = (runId: string, resolvedTraceId: string) => {
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
              traceId: resolvedTraceId || message.traceId,
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
    setChecklistItems([])
    setChecklistState('idle')
    setStreamState('idle')
    setExpandedReasoning({})
    seenEventKeysRef.current.clear()
    activeAssistantByRunRef.current.clear()
    activeAssistantFallbackIdRef.current = null
    assistantPreviewByRunRef.current.clear()
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

  const createSessionForProfile = async (
    profileId: string | null,
    role: string | null,
  ): Promise<SessionResponse> => {
    const response = await fetch(`${backendHttpUrl}/v1/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_id: profileId,
        role: role || 'member',
      }),
    })
    if (!response.ok) {
      throw new Error(`Session creation failed with status ${response.status}`)
    }
    return (await response.json()) as SessionResponse
  }

  const refreshChecklistForApplication = async (targetApplicationId: string): Promise<void> => {
    setChecklistState('loading')
    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions/${targetApplicationId}/checklist`)
      if (!response.ok) {
        throw new Error(`Checklist fetch failed with status ${response.status}`)
      }
      const payload = (await response.json()) as SessionChecklistResponse
      setChecklistItems(payload.items)
      setThreadId(payload.langgraph_thread_id)
      setWorkflowId(payload.workflow_id)
      setTraceId(payload.langsmith_trace_id)
      setChecklistState('idle')
      upsertConversation(targetApplicationId, {
        threadId: payload.langgraph_thread_id,
        workflowId: payload.workflow_id,
        traceId: payload.langsmith_trace_id,
      })
    } catch {
      setChecklistItems([])
      setChecklistState('error')
    }
  }

  const createSession = async (event: FormEvent) => {
    event.preventDefault()
    setErrorMessage('')
    setIsIncognito(false)

    try {
      const payload = await createSessionForProfile(sessionProfileId || null, sessionRole || 'member')
      setApplicationId(payload.application_id)
      setApplicationIdInput(payload.application_id)
      setThreadId(payload.langgraph_thread_id)
      setWorkflowId(payload.workflow_id)
      setTraceId(payload.langsmith_trace_id)
      clearSockets()
      resetSessionRuntime()
      upsertConversation(payload.application_id, {
        threadId: payload.langgraph_thread_id,
        workflowId: payload.workflow_id,
        traceId: payload.langsmith_trace_id,
        activeProfileId: payload.profile_id,
        isIncognito: false,
      })
      appendSystemMessage(`Session created for ${payload.application_id}`)
      if (payload.langgraph_thread_id) {
        await refreshChecklistForApplication(payload.application_id)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown session creation error')
    }
  }

  const attachSession = async (event: FormEvent) => {
    event.preventDefault()
    setErrorMessage('')
    setIsIncognito(false)
    if (!applicationIdInput.trim()) {
      setErrorMessage('Enter an existing application ID')
      return
    }

    try {
      await attachSessionById(applicationIdInput.trim(), {
        announce: `Attached to session ${applicationIdInput.trim()}`,
      })
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown session attach error')
    }
  }

  const openConversation = async (targetApplicationId: string) => {
    if (!targetApplicationId.trim()) {
      return
    }
    setErrorMessage('')
    try {
      await attachSessionById(targetApplicationId.trim(), {
        announce: `Opened conversation ${targetApplicationId.trim()}`,
      })
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to open conversation')
    }
  }

  const resolveThreadForApplication = async (targetApplicationId: string): Promise<ThreadResponse> => {
    const response = await fetch(`${backendHttpUrl}/v1/sessions/${targetApplicationId}/thread`, {
      method: 'POST',
    })
    if (!response.ok) {
      throw new Error(`Thread resolution failed with status ${response.status}`)
    }
    return (await response.json()) as ThreadResponse
  }

  const attachSessionById = async (
    targetApplicationId: string,
    options?: { announce?: string },
  ) => {
    const response = await fetch(`${backendHttpUrl}/v1/sessions/${targetApplicationId}`)
    if (!response.ok) {
      throw new Error(`Session lookup failed with status ${response.status}`)
    }
    const payload = (await response.json()) as SessionResponse
    setApplicationId(payload.application_id)
    setApplicationIdInput(payload.application_id)
    setThreadId(payload.langgraph_thread_id)
    setWorkflowId(payload.workflow_id)
    setTraceId(payload.langsmith_trace_id)
    clearSockets()
    resetSessionRuntime()
    upsertConversation(payload.application_id, {
      threadId: payload.langgraph_thread_id,
      workflowId: payload.workflow_id,
      traceId: payload.langsmith_trace_id,
      activeProfileId: payload.profile_id,
      isIncognito,
    })
    if (options?.announce) {
      appendSystemMessage(options.announce)
    }
    if (payload.langgraph_thread_id) {
      await refreshChecklistForApplication(payload.application_id)
      await loadHistoryByApplication(payload.application_id)
    }
  }

  const resolveThread = async () => {
    if (!applicationId) {
      setErrorMessage('Create or attach to an application first')
      return
    }
    setErrorMessage('')

    try {
      const payload = await resolveThreadForApplication(applicationId)
      setThreadId(payload.langgraph_thread_id)
      setWorkflowId(payload.workflow_id)
      setTraceId(payload.langsmith_trace_id)
      upsertConversation(applicationId, {
        threadId: payload.langgraph_thread_id,
        workflowId: payload.workflow_id,
        traceId: payload.langsmith_trace_id,
      })
      appendSystemMessage(`Thread ready: ${payload.langgraph_thread_id}`)
      await refreshChecklistForApplication(applicationId)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown thread resolution error')
    }
  }

  const loadHistoryByApplication = async (targetApplicationId: string) => {
    try {
      const response = await fetch(`${backendHttpUrl}/v1/sessions/${targetApplicationId}/history?limit=300`)
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
      assistantPreviewByRunRef.current.clear()
      upsertConversation(targetApplicationId, {
        threadId: payload.langgraph_thread_id,
        workflowId: payload.workflow_id,
        traceId: payload.langsmith_trace_id,
      })
      appendSystemMessage(`Loaded ${payload.count} history entries`)
      await refreshChecklistForApplication(targetApplicationId)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unknown history fetch error')
    }
  }

  const loadHistory = async () => {
    if (!applicationId) {
      setErrorMessage('No active application ID')
      return
    }
    setErrorMessage('')
    await loadHistoryByApplication(applicationId)
  }

  const refreshChecklist = async () => {
    if (!applicationId) {
      setChecklistItems([])
      setChecklistState('idle')
      return
    }
    await refreshChecklistForApplication(applicationId)
  }

  const quickStartSession = async () => {
    setErrorMessage('')
    try {
      let activeApplicationId = applicationId
      if (!activeApplicationId) {
        const sessionPayload = await createSessionForProfile(sessionProfileId || null, sessionRole || 'member')
        setApplicationId(sessionPayload.application_id)
        setApplicationIdInput(sessionPayload.application_id)
        setThreadId(sessionPayload.langgraph_thread_id)
        setWorkflowId(sessionPayload.workflow_id)
        setTraceId(sessionPayload.langsmith_trace_id)
        clearSockets()
        resetSessionRuntime()
        upsertConversation(sessionPayload.application_id, {
          threadId: sessionPayload.langgraph_thread_id,
          workflowId: sessionPayload.workflow_id,
          traceId: sessionPayload.langsmith_trace_id,
          activeProfileId: sessionPayload.profile_id,
          isIncognito,
        })
        appendSystemMessage(`Session created for ${sessionPayload.application_id}`)
        activeApplicationId = sessionPayload.application_id
      }
      const threadPayload = await resolveThreadForApplication(activeApplicationId)
      setThreadId(threadPayload.langgraph_thread_id)
      setWorkflowId(threadPayload.workflow_id)
      setTraceId(threadPayload.langsmith_trace_id)
      upsertConversation(activeApplicationId, {
        threadId: threadPayload.langgraph_thread_id,
        workflowId: threadPayload.workflow_id,
        traceId: threadPayload.langsmith_trace_id,
        activeProfileId: selectedSender?.profileId ?? null,
        isIncognito,
      })
      await refreshChecklistForApplication(activeApplicationId)
      appendSystemMessage(`Quick start ready for ${activeApplicationId}`)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to quick-start session')
    }
  }

  const toggleIncognitoMode = async () => {
    if (isIncognito) {
      setIsIncognito(false)
      setSessionProfileId('host-user')
      setSessionRole('member')
      appendSystemMessage('Incognito mode turned off.')
      return
    }

    setErrorMessage('')
    try {
      const profileAlias = `incognito-${Math.random().toString(36).slice(2, 8)}`
      setSessionProfileId(profileAlias)
      setSessionRole('member')
      setIsIncognito(true)
      if (applicationId) {
        upsertConversation(applicationId, {
          activeProfileId: profileAlias,
          isIncognito: true,
        })
      }
      appendSystemMessage(
        applicationId
          ? `Incognito persona active: ${profileAlias}. Join this app from another tab using application_id ${applicationId}.`
          : `Incognito persona active: ${profileAlias}. Join or create a session to start chatting.`,
      )
    } catch (error) {
      setIsIncognito(false)
      setErrorMessage(error instanceof Error ? error.message : 'Unable to start incognito session')
    }
  }

  const upsertParticipant = (participantId: string, patch: Partial<Participant>) => {
    setParticipants((current) =>
      current.map((participant) =>
        participant.id === participantId ? { ...participant, ...patch } : participant,
      ),
    )
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
      const prompt = asString(payload.content)
      setMessages((current) => [
        ...current,
        {
          id: newId('user'),
          kind: 'user',
          senderProfileId: asString(payload.profile_id, 'unknown'),
          senderRole: asString(payload.role, 'member'),
          createdAt: event.timestamp,
          content: prompt,
          reasoning: '',
          includeAi: payload.include_ai !== false,
          deliveryMode: asString(payload.delivery_mode, 'thread') === 'direct' ? 'direct' : 'thread',
          recipientProfileIds: asStringArray(payload.recipient_profile_ids),
          complete: true,
        },
      ])
      if (applicationId) {
        upsertConversation(applicationId, {
          title: titleFromUserPrompt(prompt),
          summary: summarizeText(prompt, 100),
          lastUpdated: event.timestamp,
          threadId: event.thread_id ?? threadId,
          activeProfileId: asString(payload.profile_id, selectedSender?.profileId ?? ''),
          isIncognito,
        })
      }
      if (payload.include_ai === false) {
        setStreamState('idle')
      }
      return
    }

    if (event.type === 'status') {
      const statusMessage = asString(payload.message)
      if (statusMessage === 'queued_for_agent') {
        setStreamState('queued')
        return
      }
      if (statusMessage === 'agent_run_started') {
        setStreamState('generating')
        const initiatedBy = asString(payload.profile_id, 'assistant')
        ensureAssistantDraft({ initiatedBy, runId, traceId: parsedTraceId })
        return
      }
      if (statusMessage === 'pong') {
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

    if (event.type === 'checklist') {
      const items = Array.isArray(payload.items) ? payload.items : []
      const nextItems: ChecklistItem[] = items
        .filter((item): item is ChecklistItem => {
          if (!item || typeof item !== 'object') {
            return false
          }
          const candidate = item as ChecklistItem
          return typeof candidate.index === 'number' && typeof candidate.text === 'string'
        })
        .map((item) => ({
          index: item.index,
          text: item.text,
          done: Boolean(item.done),
        }))
      setChecklistItems(nextItems)
      setChecklistState('idle')
      if (applicationId) {
        upsertConversation(applicationId, {
          summary:
            nextItems.length > 0
              ? `${nextItems.filter((item) => item.done).length}/${nextItems.length} tasks complete`
              : 'Checklist cleared',
          lastUpdated: event.timestamp,
          threadId: event.thread_id ?? threadId,
          workflowId: runId || workflowId,
          traceId: parsedTraceId || traceId,
        })
      }
      return
    }

    if (event.type === 'content') {
      setStreamState('generating')
      const initiatedBy = asString(payload.initiated_by_profile_id, 'assistant')
      const targetId = ensureAssistantDraft({ initiatedBy, runId, traceId: parsedTraceId })
      const delta = asString(payload.delta)
      const previewKey = runId || targetId
      const currentPreview = assistantPreviewByRunRef.current.get(previewKey) ?? ''
      const nextPreview = `${currentPreview}${delta}`
      assistantPreviewByRunRef.current.set(previewKey, nextPreview)
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
      if (applicationId) {
        upsertConversation(applicationId, {
          summary: summarizeText(nextPreview, 100) || 'AI is drafting a response…',
          lastUpdated: event.timestamp,
          threadId: event.thread_id ?? threadId,
          workflowId: runId || workflowId,
          traceId: parsedTraceId || traceId,
          isIncognito,
        })
      }
      return
    }

    if (event.type === 'complete') {
      setStreamState('completed')
      completeAssistantDraft(runId, parsedTraceId)
      if (runId) {
        assistantPreviewByRunRef.current.delete(runId)
      }
      if (applicationId) {
        upsertConversation(applicationId, {
          lastUpdated: event.timestamp,
          threadId: event.thread_id ?? threadId,
          workflowId: runId || workflowId,
          traceId: parsedTraceId || traceId,
        })
      }
      void refreshChecklist()
      return
    }

    if (event.type === 'error') {
      setStreamState('error')
      activeAssistantByRunRef.current.clear()
      activeAssistantFallbackIdRef.current = null
      appendSystemMessage(asString(payload.message, 'Unknown stream error'))
    }
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

  const connectAllParticipants = () => {
    for (const participant of participants) {
      connectParticipant(participant.id)
    }
  }

  const disconnectAllParticipants = () => {
    for (const participant of participants) {
      disconnectParticipant(participant.id)
    }
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

  useEffect(() => {
    if (urlAttachHandledRef.current) {
      return
    }
    urlAttachHandledRef.current = true
    const appFromUrl = new URLSearchParams(window.location.search).get('app')
    if (!appFromUrl) {
      return
    }
    setApplicationIdInput(appFromUrl)
    void openConversation(appFromUrl)
    // URL-based auto-attach should run once on first mount only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return {
    sessionProfileId,
    sessionRole,
    applicationIdInput,
    applicationId,
    threadId,
    workflowId,
    traceId,
    participants,
    roster,
    selectedSenderId,
    senderOptions,
    selectedSender,
    connectedParticipantIds,
    connectionSummary,
    messageInput,
    deliveryMode,
    recipientCsv,
    includeAi,
    availableRecipientProfiles,
    messages,
    events,
    expandedReasoning,
    streamState,
    errorMessage,
    checklistItems,
    checklistState,
    isIncognito,
    conversations,
    transcriptRef,
    eventLogRef,
    setSessionProfileId,
    setSessionRole,
    setApplicationIdInput,
    setSelectedSenderId,
    setDeliveryMode,
    setRecipientCsv,
    setIncludeAi,
    setMessageInput,
    createSession,
    attachSession,
    openConversation,
    quickStartSession,
    resolveThread,
    loadHistory,
    refreshChecklist,
    toggleIncognitoMode,
    connectParticipant,
    connectAllParticipants,
    disconnectAllParticipants,
    disconnectParticipant,
    addParticipant,
    removeParticipant,
    updateParticipantField,
    broadcastPing,
    sendMessage,
    sendConcurrentAiBurst,
    toggleReasoning,
  }
}
