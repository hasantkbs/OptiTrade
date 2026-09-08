import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AddCashDialog } from './AddCashDialog'
import { portfolioApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  portfolioApi: { deposit: vi.fn() },
}))

const mockedPortfolioApi = vi.mocked(portfolioApi)

const depositTransaction = {
  id: 1,
  portfolio_id: 7,
  transaction_type: 'deposit' as const,
  symbol: null,
  quantity: null,
  price: null,
  amount: 10000,
  fee: 0,
  tax: 0,
  currency: 'USD',
  executed_at: '2026-01-01T00:00:00Z',
  notes: '',
  created_at: '2026-01-01T00:00:00Z',
}

function renderDialog(open = true, onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidateSpy = vi.spyOn(client, 'invalidateQueries')
  return {
    onClose,
    invalidateSpy,
    ...render(
      <QueryClientProvider client={client}>
        <AddCashDialog portfolioId={7} baseCurrency="USD" open={open} onClose={onClose} />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AddCashDialog', () => {
  it('renders nothing when closed', () => {
    renderDialog(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders with Amount, Currency (pre-filled with the portfolio base currency), and Notes fields', () => {
    renderDialog()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText('Amount')).toBeInTheDocument()
    expect(screen.getByLabelText('Currency')).toHaveValue('USD')
    expect(screen.getByLabelText('Notes (optional)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add cash' })).toBeInTheDocument()
  })

  it('requires a non-blank amount and never calls the API for a blank submission', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.click(screen.getByRole('button', { name: 'Add cash' }))
    expect(await screen.findByText('Amount is required.')).toBeInTheDocument()
    expect(mockedPortfolioApi.deposit).not.toHaveBeenCalled()
  })

  it('rejects a zero or negative amount', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.type(screen.getByLabelText('Amount'), '0')
    await user.click(screen.getByRole('button', { name: 'Add cash' }))
    expect(await screen.findByText('Amount must be a number greater than 0.')).toBeInTheDocument()
    expect(mockedPortfolioApi.deposit).not.toHaveBeenCalled()
  })

  it('rejects a non-finite amount', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.type(screen.getByLabelText('Amount'), 'Infinity')
    await user.click(screen.getByRole('button', { name: 'Add cash' }))
    expect(await screen.findByText('Amount must be a number greater than 0.')).toBeInTheDocument()
    expect(mockedPortfolioApi.deposit).not.toHaveBeenCalled()
  })

  it('rejects a non-numeric amount', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.type(screen.getByLabelText('Amount'), 'abc')
    await user.click(screen.getByRole('button', { name: 'Add cash' }))
    expect(await screen.findByText('Amount must be a number greater than 0.')).toBeInTheDocument()
    expect(mockedPortfolioApi.deposit).not.toHaveBeenCalled()
  })

  it('submits the exact POST /portfolios/{id}/deposit request body for the correct portfolio', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.deposit.mockResolvedValueOnce(depositTransaction)
    renderDialog()

    await user.type(screen.getByLabelText('Amount'), '10000')
    await user.type(screen.getByLabelText('Notes (optional)'), 'Initial capital')
    await user.click(screen.getByRole('button', { name: 'Add cash' }))

    await waitFor(() =>
      expect(mockedPortfolioApi.deposit).toHaveBeenCalledWith(7, {
        amount: 10000,
        currency: 'USD',
        notes: 'Initial capital',
      }),
    )
  })

  it('invalidates the portfolio dashboard and transaction history queries on success', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.deposit.mockResolvedValueOnce(depositTransaction)
    const { invalidateSpy, onClose } = renderDialog()

    await user.type(screen.getByLabelText('Amount'), '10000')
    await user.click(screen.getByRole('button', { name: 'Add cash' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['dashboard', 'portfolio', 7] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['portfolios', 7, 'transactions'] })
  })

  it('shows the backend error and keeps the dialog open on failure', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.deposit.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: 'amount must be greater than 0' } },
    })
    const { onClose } = renderDialog()

    await user.type(screen.getByLabelText('Amount'), '10000')
    await user.click(screen.getByRole('button', { name: 'Add cash' }))

    expect(await screen.findByText('amount must be greater than 0')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('calls onClose when Cancel is clicked, without calling the API', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
    expect(mockedPortfolioApi.deposit).not.toHaveBeenCalled()
  })
})
