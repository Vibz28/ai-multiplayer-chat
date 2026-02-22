import { render, screen } from '@testing-library/react'

import App from './App'

describe('App', () => {
  it('renders chat-first dashboard shell', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Collaborative AI Chat' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Toggle light and dark theme' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Conversation' })).toBeInTheDocument()
  })
})
