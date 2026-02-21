import { render, screen } from '@testing-library/react'

import App from './App'

describe('App', () => {
  it('renders foundation console heading', () => {
    render(<App />)
    expect(screen.getByText('AI Multiplayer Chat Foundation Console')).toBeInTheDocument()
  })
})
