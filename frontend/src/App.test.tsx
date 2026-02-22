import { render, screen } from '@testing-library/react'

import App from './App'

describe('App', () => {
  it('renders phase 3 multiplayer heading', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Multiplayer WebSocket Chat Lab' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Toggle light and dark theme' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'WebSocket Event Trace' })).toBeInTheDocument()
  })
})
