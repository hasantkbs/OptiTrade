import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'
import { tokenStorage } from '../api/client'
import { authApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  authApi: {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
    register: vi.fn(),
    guest: vi.fn(),
  },
}))

const mockedAuthApi = vi.mocked(authApi)

const user = {
  id: 1,
  email: 'trader@optitrade.io',
  display_name: 'Trader',
  is_email_verified: true,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  last_login_at: null,
}

const guestUser = {
  id: 603,
  email: 'guest@optitrade.app',
  display_name: 'Guest',
  is_email_verified: false,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  last_login_at: null,
}

const guestTokens = { access_token: 'guest-access', refresh_token: 'guest-refresh', token_type: 'bearer', expires_in: 900 }

function Probe() {
  const { status, user: currentUser, login, logout, loginError } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="user">{currentUser?.email ?? 'none'}</span>
      <span data-testid="error">{loginError ?? 'none'}</span>
      <button
        onClick={() => {
          // AuthContext.login() deliberately rethrows after recording
          // loginError, so a real caller (LoginPage) can manage its own
          // submitting state - this probe mimics that same catch, same
          // as the real page does, so the rejection isn't left unhandled.
          login('trader@optitrade.io', 'password123').catch(() => {})
        }}
      >
        login
      </button>
      <button onClick={() => void logout()}>logout</button>
    </div>
  )
}

/** AuthProvider now reads `useQueryClient()` (to clear the cache on
 * logout/session-expiry - WEB STEP 8), so it must be rendered inside a
 * real QueryClientProvider even in these auth-only tests. */
function renderAuth() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return { client, ...render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  ) }
}

beforeEach(() => {
  vi.clearAllMocks()
  tokenStorage.clear()
})

describe('AuthProvider', () => {
  it('auto-authenticates as the shared guest account when no stored session exists - no login screen in the normal path', async () => {
    mockedAuthApi.guest.mockResolvedValueOnce(guestTokens)
    mockedAuthApi.me.mockResolvedValueOnce(guestUser)

    renderAuth()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('user')).toHaveTextContent('guest@optitrade.app')
    expect(mockedAuthApi.login).not.toHaveBeenCalled()
  })

  it('restores an authenticated session when a stored token is still valid', async () => {
    tokenStorage.setTokens({ access_token: 'a', refresh_token: 'b' })
    mockedAuthApi.me.mockResolvedValueOnce(user)

    renderAuth()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('user')).toHaveTextContent('trader@optitrade.io')
    expect(mockedAuthApi.guest).not.toHaveBeenCalled()
  })

  it('falls through to a fresh guest auto-login when a stored token is rejected by the backend', async () => {
    tokenStorage.setTokens({ access_token: 'stale', refresh_token: 'stale' })
    mockedAuthApi.me.mockRejectedValueOnce(new Error('401'))
    mockedAuthApi.guest.mockResolvedValueOnce(guestTokens)
    mockedAuthApi.me.mockResolvedValueOnce(guestUser)

    renderAuth()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('user')).toHaveTextContent('guest@optitrade.app')
    expect(tokenStorage.getAccessToken()).toBe('guest-access')
  })

  it('logs in successfully over the guest session and stores the new token pair', async () => {
    mockedAuthApi.guest.mockResolvedValueOnce(guestTokens)
    mockedAuthApi.me.mockResolvedValueOnce(guestUser)

    renderAuth()
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('guest@optitrade.app'))

    mockedAuthApi.login.mockResolvedValueOnce({
      access_token: 'new-access',
      refresh_token: 'new-refresh',
      token_type: 'bearer',
      expires_in: 900,
    })
    mockedAuthApi.me.mockResolvedValueOnce(user)

    await act(async () => {
      await userEvent.click(screen.getByText('login'))
    })

    expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    expect(screen.getByTestId('user')).toHaveTextContent('trader@optitrade.io')
    expect(tokenStorage.getAccessToken()).toBe('new-access')
  })

  it('surfaces a login error without leaking credentials, leaving the guest session active', async () => {
    mockedAuthApi.guest.mockResolvedValueOnce(guestTokens)
    mockedAuthApi.me.mockResolvedValueOnce(guestUser)

    renderAuth()
    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('guest@optitrade.app'))

    mockedAuthApi.login.mockRejectedValueOnce(new Error('invalid email or password'))

    await act(async () => {
      await userEvent.click(screen.getByText('login'))
    })

    expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    expect(screen.getByTestId('user')).toHaveTextContent('guest@optitrade.app')
    expect(screen.getByTestId('error')).not.toHaveTextContent('none')
  })

  it('logs out and silently re-authenticates as a fresh guest session, never stranding the visitor on /login', async () => {
    tokenStorage.setTokens({ access_token: 'a', refresh_token: 'b' })
    mockedAuthApi.me.mockResolvedValueOnce(user)
    mockedAuthApi.logout.mockRejectedValueOnce(new Error('network error'))
    mockedAuthApi.guest.mockResolvedValueOnce(guestTokens)
    mockedAuthApi.me.mockResolvedValueOnce(guestUser)

    renderAuth()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))

    await act(async () => {
      await userEvent.click(screen.getByText('logout'))
    })

    await waitFor(() => expect(screen.getByTestId('user')).toHaveTextContent('guest@optitrade.app'))
    expect(tokenStorage.getAccessToken()).toBe('guest-access')
  })

  it('clears the TanStack Query cache on logout, so a previous session\'s data can never leak into the next one', async () => {
    tokenStorage.setTokens({ access_token: 'a', refresh_token: 'b' })
    mockedAuthApi.me.mockResolvedValueOnce(user)
    mockedAuthApi.logout.mockResolvedValueOnce({ status: 'ok' })
    mockedAuthApi.guest.mockResolvedValueOnce(guestTokens)
    mockedAuthApi.me.mockResolvedValueOnce(guestUser)

    const { client } = renderAuth()
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))

    client.setQueryData(['portfolios'], [{ id: 1, name: 'Previous user portfolio' }])
    expect(client.getQueryData(['portfolios'])).toBeDefined()

    await act(async () => {
      await userEvent.click(screen.getByText('logout'))
    })

    expect(client.getQueryData(['portfolios'])).toBeUndefined()
  })
})
