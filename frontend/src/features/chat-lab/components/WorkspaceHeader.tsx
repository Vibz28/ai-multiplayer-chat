import type { CSSProperties } from 'react'

import type { Participant } from '../../../types'
import type { ThemeMode } from '../utils/chatLabUtils'
import { profileHue } from '../utils/presentation'

export type ScreenMode = 'chat' | 'studio'

type WorkspaceHeaderProps = {
  participants: Participant[]
  selectedSenderId: string
  isIncognito: boolean
  screenMode: ScreenMode
  themeMode: ThemeMode
  onSelectSender: (senderId: string) => void
  onToggleIncognito: () => Promise<void>
  onSelectScreen: (mode: ScreenMode) => void
  onToggleTheme: () => void
}

export function WorkspaceHeader({
  participants,
  selectedSenderId,
  isIncognito,
  screenMode,
  themeMode,
  onSelectSender,
  onToggleIncognito,
  onSelectScreen,
  onToggleTheme,
}: WorkspaceHeaderProps) {
  return (
    <header className="app-topbar panel">
      <div className="app-title">
        <p className="kicker">Multiplayer AI Workspace</p>
        <h1>Collaborative AI Chat</h1>
        <p className="subtitle">Chat-first workspace for user-to-user and user-to-agent collaboration.</p>
      </div>

      <nav className="mode-switch" aria-label="Application screens">
        <button
          type="button"
          className={screenMode === 'chat' ? 'tab active' : 'tab'}
          onClick={() => onSelectScreen('chat')}
        >
          Chat Workspace
        </button>
        <button
          type="button"
          className={screenMode === 'studio' ? 'tab active' : 'tab'}
          onClick={() => onSelectScreen('studio')}
        >
          Control Studio
        </button>
      </nav>

      <div className="top-actions">
        <div className="profile-icons" aria-label="Profile switcher">
          {participants.map((participant) => (
            <button
              key={participant.id}
              type="button"
              className={participant.id === selectedSenderId ? 'profile-icon active' : 'profile-icon'}
              style={{ '--persona-hue': `${profileHue(participant.profileId)}deg` } as CSSProperties}
              title={`${participant.profileId} (${participant.role})`}
              onClick={() => onSelectSender(participant.id)}
            >
              {participant.profileId.slice(0, 2).toUpperCase()}
            </button>
          ))}
        </div>

        <label className="incognito-toggle">
          <input type="checkbox" checked={isIncognito} onChange={() => void onToggleIncognito()} />
          <span>Incognito</span>
        </label>

        <button type="button" className="ghost" onClick={onToggleTheme} aria-label="Toggle light and dark theme">
          {themeMode === 'light' ? 'Dark mode' : 'Light mode'}
        </button>
      </div>
    </header>
  )
}
