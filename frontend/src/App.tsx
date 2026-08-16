import { useEffect, useRef, useState } from 'react'

import './App.css'
import { MarkdownMermaid } from './components/MarkdownMermaid'
import { useWorkerRoom } from './features/worker-room/useWorkerRoom'

type IconProps = { name: 'arrow' | 'check' | 'copy' | 'download' | 'menu' | 'mic' | 'people' | 'plus' | 'send' | 'shield' }

function Icon({ name }: IconProps) {
  const paths: Record<IconProps['name'], React.ReactNode> = {
    arrow: <path d="m9 18 6-6-6-6" />,
    check: <path d="m5 12 4 4L19 6" />,
    copy: <><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" /></>,
    download: <><path d="M12 3v12m0 0 5-5m-5 5-5-5" /><path d="M5 20h14" /></>,
    menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
    mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
    people: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></>,
    plus: <path d="M12 5v14M5 12h14" />,
    send: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" /><path d="m9 12 2 2 4-4" /></>,
  }

  return <svg aria-hidden="true" viewBox="0 0 24 24">{paths[name]}</svg>
}

function initials(name: string) {
  return name.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
}

function App() {
  const room = useWorkerRoom()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [shareNotice, setShareNotice] = useState('')
  const [isListening, setIsListening] = useState(false)
  const recognitionRef = useRef<{ stop: () => void } | null>(null)
  const feedRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => () => recognitionRef.current?.stop(), [])

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' })
  }, [room.messages, room.streamState])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [room.applicationId])

  const copyInvite = async () => {
    if (!room.inviteUrl) return
    await navigator.clipboard.writeText(room.inviteUrl)
    setShareNotice('Invite copied')
    window.setTimeout(() => setShareNotice(''), 1800)
  }

  const startDictation = () => {
    if (isListening) {
      recognitionRef.current?.stop()
      return
    }

    const SpeechRecognition = (window as unknown as {
      SpeechRecognition?: new () => {
        continuous: boolean
        interimResults: boolean
        lang: string
        onresult: (event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void
        onend: () => void
        start: () => void
        stop: () => void
      }
      webkitSpeechRecognition?: new () => {
        continuous: boolean
        interimResults: boolean
        lang: string
        onresult: (event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void
        onend: () => void
        start: () => void
        stop: () => void
      }
    }).SpeechRecognition ?? (window as unknown as { webkitSpeechRecognition?: new () => never }).webkitSpeechRecognition

    if (!SpeechRecognition) {
      room.setError('Voice dictation is not available here. Try the microphone on your phone keyboard.')
      return
    }

    const recognition = new SpeechRecognition()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results).map((result) => result[0].transcript).join(' ')
      room.setDraft(transcript)
    }
    recognition.onend = () => {
      recognitionRef.current = null
      setIsListening(false)
    }
    recognitionRef.current = recognition
    setIsListening(true)
    recognition.start()
  }

  const send = (event: React.FormEvent) => {
    event.preventDefault()
    room.sendMessage()
  }

  const friendlyStatus = room.streamState === 'queued'
    ? 'Lining up your request'
    : room.streamState === 'reasoning'
      ? 'Working through the details'
      : room.streamState === 'generating'
        ? 'Putting the response together'
        : room.streamState === 'error'
          ? 'Needs your attention'
          : 'Ready for work'

  return (
    <main className="app-shell">
      <header className="site-header">
        <button className="brand" type="button" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
          <span className="brand-mark"><span /></span>
          <span>Fieldwork</span>
        </button>

        <div className="header-room">
          <span className={`presence-dot ${room.connectionState}`} />
          <span>{room.applicationId ? 'Moss is online' : 'Your private worker'}</span>
        </div>

        <div className="header-actions">
          {room.applicationId && (
            <button className="quiet-button share-button" type="button" onClick={() => void copyInvite()}>
              <Icon name="people" />
              <span>{shareNotice || 'Invite someone'}</span>
            </button>
          )}
          <button className="icon-button" type="button" aria-label="Open worker settings" onClick={() => setSettingsOpen(true)}>
            <Icon name="menu" />
          </button>
        </div>
      </header>

      {!room.applicationId ? (
        <section className="welcome-layout">
          <div className="welcome-copy">
            <p className="eyebrow">A digital worker, not another dashboard</p>
            <h1>Hand off the work.<br /><em>Stay in the conversation.</em></h1>
            <p className="welcome-lede">Moss works from a private sandbox, keeps everyone in the loop, and brings back finished work you can understand and review.</p>
            <button className="primary-button start-button" type="button" onClick={() => void room.startRoom()} disabled={room.isStarting}>
              <span>{room.isStarting ? 'Preparing your room...' : 'Meet Moss'}</span>
              <Icon name="arrow" />
            </button>
            {room.error && <p className="inline-error" role="alert">{room.error}</p>}
          </div>

          <div className="welcome-portrait" aria-label="Moss, your digital worker">
            <div className="portrait-card">
              <div className="portrait-scene">
                <span className="sun-disc" />
                <span className="hill hill-back" />
                <span className="hill hill-front" />
                <span className="worker-orb"><span /></span>
              </div>
              <div className="portrait-caption">
                <div>
                  <p className="eyebrow">Your worker</p>
                  <h2>Moss</h2>
                </div>
                <span className="available-pill"><span /> Available</span>
              </div>
            </div>
            <div className="trust-note"><Icon name="shield" /><span>Works inside a restricted sandbox. High-impact actions stay with you.</span></div>
          </div>
        </section>
      ) : (
        <section className="room-layout">
          <section className="conversation-column">
            <div className="worker-intro">
              <div className="worker-avatar"><span /></div>
              <div>
                <p className="eyebrow">Shared workroom</p>
                <h1>Moss</h1>
                <p>{friendlyStatus}</p>
              </div>
              <div className="room-people" aria-label={`${room.roster.length} people connected`}>
                {room.roster.slice(0, 3).map((person) => <span key={person.profile_id}>{initials(person.profile_id)}</span>)}
                <span className="moss-mini">M</span>
              </div>
            </div>

            <div className="message-feed" ref={feedRef} aria-live="polite">
              {room.messages.length === 0 && (
                <div className="empty-conversation">
                  <p className="eyebrow">Moss is ready</p>
                  <h2>What should we make progress on?</h2>
                  <p>Describe the outcome in your own words. Moss will plan the work, keep this room updated, and return something reviewable.</p>
                  <div className="suggestion-list">
                    {[
                      'Review this project and suggest the highest-impact improvement',
                      'Turn a rough idea into a clear plan and first draft',
                      'Investigate a bug and explain the fix without jargon',
                    ].map((suggestion) => (
                      <button key={suggestion} type="button" onClick={() => room.setDraft(suggestion)}>{suggestion}<Icon name="arrow" /></button>
                    ))}
                  </div>
                </div>
              )}

              {room.messages.map((message) => {
                if (message.kind === 'system') {
                  return <p className="system-message" key={message.id}>{message.content}</p>
                }
                const assistant = message.kind === 'assistant'
                return (
                  <article className={`message ${assistant ? 'from-worker' : 'from-person'}`} key={message.id}>
                    {assistant && <div className="message-avatar worker-avatar small"><span /></div>}
                    <div className="message-body">
                      <header>
                        <strong>{assistant ? 'Moss' : message.senderProfileId}</strong>
                        <time>{new Date(message.createdAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
                      </header>
                      <div className="message-bubble">
                        {assistant ? <MarkdownMermaid markdown={message.content || '_Working on it..._'} /> : <p>{message.content}</p>}
                      </div>
                      {assistant && !message.complete && <span className="working-label"><i /><i /><i /> Moss is working</span>}
                    </div>
                  </article>
                )
              })}
            </div>

            <form className="composer" onSubmit={send}>
              <textarea
                aria-label="Message Moss and your group"
                value={room.draft}
                onChange={(event) => room.setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    room.sendMessage()
                  }
                }}
                placeholder="Ask Moss to take something on..."
                rows={2}
              />
              <div className="composer-footer">
                <div className="composer-context"><span className={`presence-dot ${room.connectionState}`} />{room.connectionState === 'online' ? `Working with ${room.harness}` : 'Reconnecting to the room'}</div>
                <div className="composer-actions">
                  <button className={`icon-button mic-button ${isListening ? 'listening' : ''}`} type="button" aria-label="Dictate a message" onClick={startDictation}><Icon name="mic" /></button>
                  <button className="send-button" type="submit" aria-label="Send message" disabled={!room.draft.trim() || room.connectionState !== 'online'}><Icon name="send" /></button>
                </div>
              </div>
            </form>
            {room.error && <p className="inline-error room-error" role="alert">{room.error}</p>}
          </section>

          <aside className="work-column">
            <section className="work-card">
              <header><div><p className="eyebrow">Current assignment</p><h2>Work in progress</h2></div><span>{room.completedCount}/{room.checklist.length || 0}</span></header>
              {room.checklist.length > 0 ? (
                <ol className="work-list">
                  {room.checklist.map((item) => (
                    <li className={item.done ? 'complete' : ''} key={`${item.index}-${item.text}`}>
                      <span>{item.done ? <Icon name="check" /> : item.index}</span>
                      <p>{item.text}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <div className="empty-work"><span className="paper-stack"><i /><i /><i /></span><p>When Moss takes on a larger task, the important steps will appear here.</p></div>
              )}
            </section>

            {room.artifacts.length > 0 && (
              <section className="deliverables-card">
                <header><p className="eyebrow">Ready to review</p><h2>Deliverables</h2></header>
                <div className="deliverable-list">
                  {room.artifacts.map((artifact) => (
                    <a href="#" key={artifact.artifact_id} onClick={(event) => { event.preventDefault(); void room.downloadArtifact(artifact) }}>
                      <span><strong>{artifact.title}</strong><small>{artifact.filename} · {Math.max(1, Math.round(artifact.size_bytes / 1024))} KB</small></span>
                      <Icon name="download" />
                    </a>
                  ))}
                </div>
              </section>
            )}

            <section className="boundary-card">
              <Icon name="shield" />
              <div><h3>You keep the final say</h3><p>Moss can prepare files and evidence in its sandbox. Publishing, repository administration, and privileged changes stay outside the worker.</p></div>
            </section>

            <button className="new-room-button" type="button" onClick={() => void room.startNewRoom()}><Icon name="plus" /> Start a fresh room</button>
          </aside>
        </section>
      )}

      {settingsOpen && (
        <div className="sheet-backdrop" role="presentation" onMouseDown={() => setSettingsOpen(false)}>
          <aside className="settings-sheet" role="dialog" aria-modal="true" aria-label="Worker settings" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><p className="eyebrow">Worker details</p><h2>How Moss works</h2></div><button className="icon-button close-button" type="button" aria-label="Close settings" onClick={() => setSettingsOpen(false)}>×</button></header>

            <label className="field-label">Your display name<input value={room.profileName} maxLength={64} onChange={(event) => room.setProfileName(event.target.value)} /></label>

            <fieldset className="harness-picker">
              <legend>Preferred agent harness</legend>
              <p>The platform model router resolves cloud models and compatible subscription grants for each sandboxed harness.</p>
              {(['Moss Cloud', 'Codex', 'Claude Code', 'OpenCode', 'Pi'] as const).map((option) => {
                const route = room.harnessRoutes[option]
                const unavailable = route?.available === false
                const description = unavailable
                  ? route.reason ?? 'No compatible platform grant is configured.'
                  : option === 'Moss Cloud'
                    ? 'Shared cloud route, no local model'
                    : option === 'Codex'
                      ? 'Uses the ChatGPT platform account'
                      : option === 'Claude Code'
                        ? 'Uses the Claude platform account'
                        : `Uses ${route?.provider?.replaceAll('_', ' ') ?? 'a compatible platform route'}`
                return (
                  <label key={option} className={`${room.harness === option ? 'selected' : ''} ${unavailable ? 'disabled' : ''}`}>
                    <input type="radio" name="harness" checked={room.harness === option} disabled={unavailable} onChange={() => room.setHarness(option)} />
                    <span><strong>{option}</strong><small>{description}</small></span>
                    {room.harness === option && <Icon name="check" />}
                  </label>
                )
              })}
            </fieldset>

            <section className="permission-box"><Icon name="shield" /><div><strong>Writer, never administrator</strong><p>The worker runs without host credentials, Docker access, or repository administration permissions.</p></div></section>

            {room.applicationId && <button className="copy-room-button" type="button" onClick={() => void copyInvite()}><Icon name="copy" /> {shareNotice || 'Copy room invite'}</button>}
            <details className="technical-details"><summary>Technical details</summary><code>{room.applicationId || 'No active room'}</code><p>WebSocket reconnects automatically and the room ID persists on this device.</p></details>
          </aside>
        </div>
      )}
    </main>
  )
}

export default App
