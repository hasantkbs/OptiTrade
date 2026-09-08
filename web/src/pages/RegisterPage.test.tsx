import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RegisterPage } from './RegisterPage'
import { LoginPage } from './LoginPage'
import { AuthProvider } from '../auth/AuthContext'
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

const createdUser = {
  id: 1,
  email: 'trader@optitrade.io',
  display_name: 'trader',
  is_email_verified: false,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  last_login_at: null,
}

/** Renders /register with a real /login route alongside it - the
 * post-registration redirect (RegisterPage -> /login with a success
 * message) is real navigation, not mocked, so this is the only way to
 * actually observe it. */
function renderRegister() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/register']}>
        <AuthProvider>
          <Routes>
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/login" element={<LoginPage />} />
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

describe('RegisterPage', () => {
  it('renders email, password, confirm password, a submit button, and a link back to sign in', async () => {
    renderRegister()
    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('rejects an empty submission without calling the API', async () => {
    const user = userEvent.setup()
    renderRegister()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Email is required.')).toBeInTheDocument()
    expect(screen.getByText('Password is required.')).toBeInTheDocument()
    expect(mockedAuthApi.register).not.toHaveBeenCalled()
  })

  it('rejects an invalid email format without calling the API', async () => {
    const user = userEvent.setup()
    renderRegister()
    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())

    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.type(screen.getByLabelText('Password'), 'Password123')
    await user.type(screen.getByLabelText('Confirm password'), 'Password123')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(mockedAuthApi.register).not.toHaveBeenCalled()
  })

  it('rejects a mismatched confirm password without calling the API', async () => {
    const user = userEvent.setup()
    renderRegister()
    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())

    await user.type(screen.getByLabelText('Email'), 'trader@optitrade.io')
    await user.type(screen.getByLabelText('Password'), 'Password123')
    await user.type(screen.getByLabelText('Confirm password'), 'Different123')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument()
    expect(mockedAuthApi.register).not.toHaveBeenCalled()
  })

  it('registers with the real /auth/register contract and redirects to /login with a success message', async () => {
    const user = userEvent.setup()
    mockedAuthApi.register.mockResolvedValueOnce(createdUser)
    renderRegister()
    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())

    await user.type(screen.getByLabelText('Email'), 'trader@optitrade.io')
    await user.type(screen.getByLabelText('Password'), 'Password123')
    await user.type(screen.getByLabelText('Confirm password'), 'Password123')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() =>
      expect(mockedAuthApi.register).toHaveBeenCalledWith({
        email: 'trader@optitrade.io',
        password: 'Password123',
        display_name: 'trader',
      }),
    )
    // Registration only creates the account (POST /auth/register returns
    // UserResponse, not a session) - it must never call login/establish
    // a session itself.
    expect(mockedAuthApi.login).not.toHaveBeenCalled()
    expect(await screen.findByText('Account created. Sign in to continue.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows the backend error and stays on the page for a duplicate email', async () => {
    const user = userEvent.setup()
    mockedAuthApi.register.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: 'trader@optitrade.io is already registered' } },
    })
    renderRegister()
    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument())

    await user.type(screen.getByLabelText('Email'), 'trader@optitrade.io')
    await user.type(screen.getByLabelText('Password'), 'Password123')
    await user.type(screen.getByLabelText('Confirm password'), 'Password123')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('trader@optitrade.io is already registered')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
  })
})

describe('Sign in / Create account navigation', () => {
  it('links from the login page to /register and back', async () => {
    const user = userEvent.setup()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/login']}>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument())
    await user.click(screen.getByRole('link', { name: 'Create account' }))

    expect(await screen.findByRole('button', { name: 'Create account' })).toBeInTheDocument()
  })
})
