import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CreateWatchlistDialog } from './CreateWatchlistDialog'
import { watchlistApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  watchlistApi: { create: vi.fn() },
}))

const mockedWatchlistApi = vi.mocked(watchlistApi)

function renderDialog(open = true, onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <CreateWatchlistDialog open={open} onClose={onClose} />
      </QueryClientProvider>,
    ),
  }
}

const created = { id: 1, owner: 'trader@optitrade.io', name: 'Core Holdings', created_at: '2026-01-01T00:00:00Z' }

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CreateWatchlistDialog', () => {
  it('renders nothing when closed', () => {
    renderDialog(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens with a name field and both actions', () => {
    renderDialog()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText('Watchlist name')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create watchlist' })).toBeInTheDocument()
  })

  it('requires a non-blank name and never calls the API for a blank submission', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.click(screen.getByRole('button', { name: 'Create watchlist' }))
    expect(await screen.findByText('Watchlist name is required.')).toBeInTheDocument()
    expect(mockedWatchlistApi.create).not.toHaveBeenCalled()
  })

  it('creates the watchlist via the real POST /watchlists contract and closes on success', async () => {
    const user = userEvent.setup()
    mockedWatchlistApi.create.mockResolvedValueOnce(created)
    const { onClose } = renderDialog()

    await user.type(screen.getByLabelText('Watchlist name'), 'Core Holdings')
    await user.click(screen.getByRole('button', { name: 'Create watchlist' }))

    await waitFor(() => expect(mockedWatchlistApi.create).toHaveBeenCalledWith({ name: 'Core Holdings' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('shows the API error and keeps the dialog open on failure', async () => {
    const user = userEvent.setup()
    mockedWatchlistApi.create.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: 'name must not be blank' } },
    })
    const { onClose } = renderDialog()

    await user.type(screen.getByLabelText('Watchlist name'), 'Core Holdings')
    await user.click(screen.getByRole('button', { name: 'Create watchlist' }))

    expect(await screen.findByText('name must not be blank')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
  })
})
