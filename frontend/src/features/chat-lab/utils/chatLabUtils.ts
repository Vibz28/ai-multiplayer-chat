import type { ChatMessage, RosterParticipant, SessionHistoryResponse } from '../../../types'

export type ThemeMode = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'chatlab-theme'

export function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`
}

export function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

export function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((entry): entry is string => typeof entry === 'string')
}

export function parseRoster(payload: Record<string, unknown>): RosterParticipant[] {
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

export function parseRunIdentity(payload: Record<string, unknown>): { runId: string; traceId: string } {
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

export function initialTheme(): ThemeMode {
  if (typeof window === 'undefined') {
    return 'light'
  }
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') {
    return saved
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function historyToMessages(history: SessionHistoryResponse): ChatMessage[] {
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
