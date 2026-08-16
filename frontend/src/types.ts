export type StreamState = 'idle' | 'queued' | 'generating' | 'reasoning' | 'completed' | 'error'

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

export type ChecklistItem = {
  index: number
  text: string
  done: boolean
}

export type Artifact = {
  artifact_id: string
  filename: string
  title: string
  description: string
  kind: string
  media_type: string
  size_bytes: number
  sha256: string
  download_ref: string
  immutable: boolean
}

export type EventEnvelope = {
  type: string
  application_id: string
  thread_id: string | null
  stream_state: string | null
  timestamp: string
  payload: Record<string, unknown>
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
