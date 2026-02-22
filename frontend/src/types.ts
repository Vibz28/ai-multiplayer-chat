export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error'
export type StreamState = 'idle' | 'queued' | 'generating' | 'reasoning' | 'completed' | 'error'

export type SessionResponse = {
  application_id: string
  profile_id: string | null
  role: string | null
  langgraph_thread_id: string | null
  workflow_id: string | null
  langsmith_trace_id: string | null
  created_at: string
  updated_at: string
}

export type ThreadResponse = {
  application_id: string
  langgraph_thread_id: string
  workflow_id: string | null
  langsmith_trace_id: string | null
  updated_at: string
}

export type HistoryEntry = {
  application_id: string
  thread_id: string
  profile_id: string | null
  role: string
  channel: string
  content: string
  run_id: string | null
  trace_id: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export type SessionHistoryResponse = {
  application_id: string
  langgraph_thread_id: string
  profile_id: string | null
  role: string | null
  workflow_id: string | null
  langsmith_trace_id: string | null
  entries: HistoryEntry[]
  count: number
}

export type ChecklistItem = {
  index: number
  text: string
  done: boolean
}

export type SessionChecklistResponse = {
  application_id: string
  langgraph_thread_id: string
  workflow_id: string | null
  langsmith_trace_id: string | null
  items: ChecklistItem[]
  count: number
}

export type EventEnvelope = {
  type: string
  application_id: string
  thread_id: string | null
  stream_state: string | null
  timestamp: string
  payload: Record<string, unknown>
}

export type Participant = {
  id: string
  profileId: string
  role: string
  connectionState: ConnectionState
}

export type RosterParticipant = {
  profile_id: string
  role: string
  connected_at: string
}

export type ChatMessage = {
  id: string
  kind: 'user' | 'assistant' | 'system'
  senderProfileId: string
  senderRole: string
  createdAt: string
  content: string
  reasoning: string
  includeAi?: boolean
  deliveryMode?: 'thread' | 'direct'
  recipientProfileIds?: string[]
  runId?: string
  traceId?: string
  complete?: boolean
}
