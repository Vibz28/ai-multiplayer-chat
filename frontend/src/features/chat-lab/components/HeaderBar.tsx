import type { StreamState } from '../../../types'

type ThemeMode = 'light' | 'dark'

type HeaderBarProps = {
  connectionSummary: 'disconnected' | 'partial' | 'connected'
  streamState: StreamState
  themeMode: ThemeMode
  onToggleTheme: () => void
}

export function HeaderBar({
  connectionSummary,
  streamState,
  themeMode,
  onToggleTheme,
}: HeaderBarProps) {
  return (
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
          onClick={onToggleTheme}
          aria-label="Toggle light and dark theme"
        >
          {themeMode === 'light' ? 'Dark mode' : 'Light mode'}
        </button>
      </div>
    </header>
  )
}
