import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ProtectedRoute } from './ProtectedRoute'
import { AuthProvider } from './AuthContext'
import { tokenStorage } from '../api/client'
import { authApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  authApi: {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
    register: vi.fn(),
  },
}))

const mockedAuthApi = vi.mocked(authApi)

function renderProtected() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login screen</div>} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <div>Secret dashboard content</div>
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  tokenStorage.clear()
})

describe('ProtectedRoute', () => {
  it('redirects to /login when there is no session', async () => {
    renderProtected()
    await waitFor(() => expect(screen.getByText('Login screen')).toBeInTheDocument())
    expect(screen.queryByText('Secret dashboard content')).not.toBeInTheDocument()
  })

  it('renders the protected content once a session is confirmed', async () => {
    tokenStorage.setTokens({ access_token: 'a', refresh_token: 'b' })
    mockedAuthApi.me.mockResolvedValueOnce({
      id: 1,
      email: 'trader@optitrade.io',
      display_name: 'Trader',
      is_email_verified: true,
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      last_login_at: null,
    })

    renderProtected()
    await waitFor(() => expect(screen.getByText('Secret dashboard content')).toBeInTheDocument())
  })
})
