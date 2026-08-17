import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

import App from './App'

describe('App', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.history.replaceState({}, '', '/')
  })

  it('introduces the worker without exposing infrastructure controls', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /Hand off the work/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Meet Moss/i })).toBeInTheDocument()
    expect(screen.queryByText(/application_id/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Control Studio/i)).not.toBeInTheDocument()
  })

  it('creates a persistent room from the welcome screen', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/v1/sessions')) {
        return new Response(JSON.stringify({ application_id: 'app_worker_room', room_token: 'room_secret' }), { status: 201 })
      }
      if (url.includes('/history')) return new Response(JSON.stringify({ entries: [] }), { status: 200 })
      if (url.includes('/checklist')) return new Response(JSON.stringify({ items: [] }), { status: 200 })
      if (url.includes('/artifacts')) return new Response(JSON.stringify({ items: [] }), { status: 200 })
      return new Response(JSON.stringify({ application_id: 'app_worker_room' }), { status: 200 })
    })

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /Meet Moss/i }))

    await waitFor(() => expect(window.localStorage.getItem('fieldwork.room.v1')).toContain('app_worker_room'))
    expect(window.location.hash).toBe('#room=app_worker_room&key=room_secret')
    fetchMock.mockRestore()
  })

  it('clears an invalid persisted room instead of reconnecting forever', async () => {
    window.localStorage.setItem('fieldwork.room.v1', JSON.stringify({ id: 'app_stale', token: 'stale' }))
    window.history.replaceState({}, '', '/#room=app_stale&key=stale')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Invalid room capability' }), { status: 403 }),
    )

    render(<App />)

    expect(await screen.findByRole('button', { name: /Meet Moss/i })).toBeInTheDocument()
    expect(screen.getByText(/room invite is no longer valid/i)).toBeInTheDocument()
    expect(window.localStorage.getItem('fieldwork.room.v1')).toBeNull()
    expect(window.location.hash).toBe('')
    fetchMock.mockRestore()
  })
})
