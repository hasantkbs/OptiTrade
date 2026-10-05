import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { tokenStorage } from './api/client'

/**
 * Route-table-level smoke tests (WEB STEP 8 Phase 1/13 - previously
 * only `ProtectedRoute` was tested in isolation, never the real
 * `App.tsx` route table). No page-specific API mocking is needed for
 * these: with no stored session, `AuthProvider` resolves to
 * 'unauthenticated' before any protected page ever mounts, so every
 * protected/unknown path exercises the exact same real redirect chain
 * a logged-out visitor hits.
 */
function renderAppAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  tokenStorage.clear()
})

describe('App routing', () => {
  it('shows the login screen at /login', async () => {
    renderAppAt('/login')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument())
  })

  it('shows the registration screen at /register', async () => {
    renderAppAt('/register')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument())
  })

  it('redirects an unauthenticated visitor from a protected route to /login', async () => {
    renderAppAt('/watchlist')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument())
  })

  it('redirects an unauthenticated visitor from a deep protected route to /login', async () => {
    renderAppAt('/assets/AAPL')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument())
  })

  it('redirects an unknown route to / (and then, unauthenticated, on to /login)', async () => {
    renderAppAt('/this-route-does-not-exist')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument())
  })
})
