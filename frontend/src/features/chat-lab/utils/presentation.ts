import type { EventEnvelope } from '../../../types'

export type EventSummary = {
  total: number
  userMessages: number
  contentChunks: number
  reasoningChunks: number
  checklistEvents: number
  completions: number
  errors: number
}

export type EventDistributionItem = {
  key: string
  label: string
  count: number
  ratio: number
}

export function profileHue(profileId: string): number {
  let hash = 0
  for (let i = 0; i < profileId.length; i += 1) {
    hash = (hash * 33 + profileId.charCodeAt(i)) % 360
  }
  return hash
}

export function streamSummary(streamState: string): string {
  if (streamState === 'generating') {
    return 'AI is drafting a response'
  }
  if (streamState === 'reasoning') {
    return 'AI is planning and calling tools'
  }
  if (streamState === 'queued') {
    return 'Request queued'
  }
  if (streamState === 'completed') {
    return 'Response complete'
  }
  if (streamState === 'error') {
    return 'Response failed'
  }
  return 'Ready'
}

export function shortId(value: string | null): string {
  if (!value) {
    return 'n/a'
  }
  if (value.length <= 18) {
    return value
  }
  return `${value.slice(0, 8)}…${value.slice(-7)}`
}

export function summarizeEvents(events: EventEnvelope[]): EventSummary {
  const counts = new Map<string, number>()
  for (const event of events) {
    counts.set(event.type, (counts.get(event.type) ?? 0) + 1)
  }

  return {
    total: events.length,
    userMessages: counts.get('user_message') ?? 0,
    contentChunks: counts.get('content') ?? 0,
    reasoningChunks: counts.get('reasoning') ?? 0,
    checklistEvents: counts.get('checklist') ?? 0,
    completions: counts.get('complete') ?? 0,
    errors: counts.get('error') ?? 0,
  }
}

export function distributionFromSummary(summary: EventSummary): EventDistributionItem[] {
  const total = Math.max(summary.total, 1)
  const ratio = (count: number) => (count / total) * 100

  return [
    {
      key: 'user',
      label: 'User messages',
      count: summary.userMessages,
      ratio: ratio(summary.userMessages),
    },
    {
      key: 'content',
      label: 'AI content chunks',
      count: summary.contentChunks,
      ratio: ratio(summary.contentChunks),
    },
    {
      key: 'reasoning',
      label: 'Reasoning chunks',
      count: summary.reasoningChunks,
      ratio: ratio(summary.reasoningChunks),
    },
    {
      key: 'checklist',
      label: 'Checklist updates',
      count: summary.checklistEvents,
      ratio: ratio(summary.checklistEvents),
    },
    {
      key: 'complete',
      label: 'Completed runs',
      count: summary.completions,
      ratio: ratio(summary.completions),
    },
    {
      key: 'errors',
      label: 'Errors',
      count: summary.errors,
      ratio: ratio(summary.errors),
    },
  ]
}
