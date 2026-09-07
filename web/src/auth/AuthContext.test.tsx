import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

beforeEach(() => {
  vi.clearAllMocks()
  tokenStorage.clear()
})

describe('AuthProvider', () => {
  it('starts unauthenticated when no stored session exists', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))
  })

  it('restores an authenticated session when a stored token is still valid', async () => {
    tokenStorage.setTokens({ access_token: 'a', refresh_token: 'b' })
    mockedAuthApi.me.mockResolvedValueOnce(user)

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))
    expect(screen.getByTestId('user')).toHaveTextContent('trader@optitrade.io')
  })

  it('clears a stored token that the backend no longer accepts', async () => {
    tokenStorage.setTokens({ access_token: 'stale', refresh_token: 'stale' })
    mockedAuthApi.me.mockRejectedValueOnce(new Error('401'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))
    expect(tokenStorage.getAccessToken()).toBeNull()
  })

  it('logs in successfully and stores the new token pair', async () => {
    mockedAuthApi.login.mockResolvedValueOnce({
      access_token: 'new-access',
      refresh_token: 'new-refresh',
      token_type: 'bearer',
      expires_in: 900,
    })
    mockedAuthApi.me.mockResolvedValueOnce(user)

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))

    await act(async () => {
      await userEvent.click(screen.getByText('login'))
    })

    expect(screen.getByTestId('status')).toHaveTextContent('authenticated')
    expect(tokenStorage.getAccessToken()).toBe('new-access')
  })

  it('surfaces a login error without leaking credentials and stays unauthenticated', async () => {
    mockedAuthApi.login.mockRejectedValueOnce(new Error('invalid email or password'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'))

    await act(async () => {
      await userEvent.click(screen.getByText('login'))
    })

    expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated')
    expect(screen.getByTestId('error')).not.toHaveTextContent('none')
  })

  it('logs out and clears the stored session even if the network call fails', async () => {
    tokenStorage.setTokens({ access_token: 'a', refresh_token: 'b' })
    mockedAuthApi.me.mockResolvedValueOnce(user)
    mockedAuthApi.logout.mockRejectedValueOnce(new Error('network error'))

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('authenticated'))

    await act(async () => {
      await userEvent.click(screen.getByText('logout'))
    })

    expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated')
    expect(tokenStorage.getAccessToken()).toBeNull()
  })
})
