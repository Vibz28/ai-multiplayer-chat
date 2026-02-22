import { useEffect, useMemo, useState } from 'react'

import './App.css'
import { ChatWorkspace } from './features/chat-lab/components/ChatWorkspace'
import { ControlStudio } from './features/chat-lab/components/ControlStudio'
import { WorkspaceHeader, type ScreenMode } from './features/chat-lab/components/WorkspaceHeader'
import { useChatLabController } from './features/chat-lab/hooks/useChatLabController'
import { initialTheme, THEME_STORAGE_KEY, type ThemeMode } from './features/chat-lab/utils/chatLabUtils'

function App() {
  const controller = useChatLabController()
  const [themeMode, setThemeMode] = useState<ThemeMode>(initialTheme)
  const [screenMode, setScreenMode] = useState<ScreenMode>('chat')
  const [inviteStatus, setInviteStatus] = useState('')

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode
    window.localStorage.setItem(THEME_STORAGE_KEY, themeMode)
  }, [themeMode])

  const selectedSenderId = controller.selectedSender?.id ?? ''

  const shareUrl = useMemo(() => {
    if (!controller.applicationId) {
      return ''
    }
    return `${window.location.origin}${window.location.pathname}?app=${controller.applicationId}`
  }, [controller.applicationId])

  const copyShareUrl = async () => {
    if (!shareUrl || !navigator.clipboard) {
      return
    }
    try {
      await navigator.clipboard.writeText(shareUrl)
      setInviteStatus('Invite link copied')
      window.setTimeout(() => setInviteStatus(''), 1800)
    } catch {
      setInviteStatus('Copy failed')
      window.setTimeout(() => setInviteStatus(''), 1800)
    }
  }

  const openShareUrl = () => {
    if (!shareUrl) {
      return
    }
    window.open(shareUrl, '_blank', 'noopener,noreferrer')
  }

  const toggleTheme = () => {
    setThemeMode((current) => (current === 'light' ? 'dark' : 'light'))
  }

  return (
    <main className="workspace-shell">
      <WorkspaceHeader
        participants={controller.participants}
        selectedSenderId={selectedSenderId}
        isIncognito={controller.isIncognito}
        screenMode={screenMode}
        themeMode={themeMode}
        onSelectSender={controller.setSelectedSenderId}
        onToggleIncognito={controller.toggleIncognitoMode}
        onSelectScreen={setScreenMode}
        onToggleTheme={toggleTheme}
      />

      {screenMode === 'chat' ? (
        <ChatWorkspace
          controller={controller}
          inviteStatus={inviteStatus}
          shareUrl={shareUrl}
          onCopyShareUrl={copyShareUrl}
          onOpenShareUrl={openShareUrl}
          onOpenControlStudio={() => setScreenMode('studio')}
        />
      ) : (
        <ControlStudio controller={controller} />
      )}
    </main>
  )
}

export default App
