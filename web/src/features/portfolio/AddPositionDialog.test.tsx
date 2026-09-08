import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AddPositionDialog } from './AddPositionDialog'
import { portfolioApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  portfolioApi: { buy: vi.fn() },
}))

const mockedPortfolioApi = vi.mocked(portfolioApi)

const boughtTransaction = {
  id: 1,
  portfolio_id: 7,
  transaction_type: 'buy' as const,
  symbol: 'AAPL',
  quantity: 10,
  price: 210,
  amount: 2100,
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
        <AddPositionDialog portfolioId={7} open={open} onClose={onClose} />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AddPositionDialog', () => {
  it('renders nothing when closed', () => {
    renderDialog(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders with Symbol, Quantity, and Entry price fields, and both actions', () => {
    renderDialog()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText('Symbol')).toBeInTheDocument()
    expect(screen.getByLabelText('Quantity')).toBeInTheDocument()
    expect(screen.getByLabelText('Entry price')).toBeInTheDocument()
    // No current-price input must ever exist on this form.
    expect(screen.queryByLabelText(/current price/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add position' })).toBeInTheDocument()
  })

  it('requires all fields and never calls the API for a blank submission', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.click(screen.getByRole('button', { name: 'Add position' }))

    expect(await screen.findByText('Symbol is required.')).toBeInTheDocument()
    expect(screen.getByText('Quantity is required.')).toBeInTheDocument()
    expect(screen.getByText('Entry price is required.')).toBeInTheDocument()
    expect(mockedPortfolioApi.buy).not.toHaveBeenCalled()
  })

  it('rejects a zero or negative quantity', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Quantity'), '0')
    await user.type(screen.getByLabelText('Entry price'), '210')
    await user.click(screen.getByRole('button', { name: 'Add position' }))

    expect(await screen.findByText('Quantity must be a number greater than 0.')).toBeInTheDocument()
    expect(mockedPortfolioApi.buy).not.toHaveBeenCalled()
  })

  it('rejects a zero or negative entry price', async () => {
    const user = userEvent.setup()
    renderDialog()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Quantity'), '10')
    await user.type(screen.getByLabelText('Entry price'), '-5')
    await user.click(screen.getByRole('button', { name: 'Add position' }))

    expect(await screen.findByText('Entry price must be a number greater than 0.')).toBeInTheDocument()
    expect(mockedPortfolioApi.buy).not.toHaveBeenCalled()
  })

  it('normalizes a lowercase symbol to uppercase before submitting', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.buy.mockResolvedValueOnce(boughtTransaction)
    renderDialog()

    await user.type(screen.getByLabelText('Symbol'), 'aapl')
    await user.type(screen.getByLabelText('Quantity'), '10')
    await user.type(screen.getByLabelText('Entry price'), '210')
    await user.click(screen.getByRole('button', { name: 'Add position' }))

    await waitFor(() =>
      expect(mockedPortfolioApi.buy).toHaveBeenCalledWith(7, { symbol: 'AAPL', quantity: 10, price: 210 }),
    )
  })

  it('submits the exact POST /portfolios/{id}/buy request body', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.buy.mockResolvedValueOnce(boughtTransaction)
    renderDialog()

    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Quantity'), '10')
    await user.type(screen.getByLabelText('Entry price'), '210')
    await user.click(screen.getByRole('button', { name: 'Add position' }))

    await waitFor(() =>
      expect(mockedPortfolioApi.buy).toHaveBeenCalledWith(7, { symbol: 'AAPL', quantity: 10, price: 210 }),
    )
  })

  it('invalidates the portfolio dashboard and transaction history queries on success', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.buy.mockResolvedValueOnce(boughtTransaction)
    const { invalidateSpy, onClose } = renderDialog()

    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Quantity'), '10')
    await user.type(screen.getByLabelText('Entry price'), '210')
    await user.click(screen.getByRole('button', { name: 'Add position' }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['dashboard', 'portfolio', 7] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['portfolios', 7, 'transactions'] })
  })

  it('shows the backend error and keeps the dialog open on failure', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.buy.mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { detail: 'portfolio 7: cannot buy 10 AAPL at 210 - total cost 2100 exceeds available cash 0' } },
    })
    const { onClose } = renderDialog()

    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Quantity'), '10')
    await user.type(screen.getByLabelText('Entry price'), '210')
    await user.click(screen.getByRole('button', { name: 'Add position' }))

    expect(await screen.findByText(/exceeds available cash/)).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('lets the user add multiple different symbols to the same portfolio in sequence', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.buy.mockResolvedValue(boughtTransaction)
    const onClose = vi.fn()
    renderDialog(true, onClose)

    for (const symbol of ['AAPL', 'NVDA', 'MSFT']) {
      await user.type(screen.getByLabelText('Symbol'), symbol)
      await user.type(screen.getByLabelText('Quantity'), '10')
      await user.type(screen.getByLabelText('Entry price'), '100')
      await user.click(screen.getByRole('button', { name: 'Add position' }))
      await waitFor(() => expect(onClose).toHaveBeenCalledTimes(['AAPL', 'NVDA', 'MSFT'].indexOf(symbol) + 1))
    }

    expect(mockedPortfolioApi.buy).toHaveBeenCalledTimes(3)
    expect(mockedPortfolioApi.buy).toHaveBeenNthCalledWith(1, 7, { symbol: 'AAPL', quantity: 10, price: 100 })
    expect(mockedPortfolioApi.buy).toHaveBeenNthCalledWith(2, 7, { symbol: 'NVDA', quantity: 10, price: 100 })
    expect(mockedPortfolioApi.buy).toHaveBeenNthCalledWith(3, 7, { symbol: 'MSFT', quantity: 10, price: 100 })
  })

  it('accepts the same symbol submitted twice without any client-side duplicate rejection', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.buy.mockResolvedValue(boughtTransaction)
    const onClose = vi.fn()
    renderDialog(true, onClose)

    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Quantity'), '10')
    await user.type(screen.getByLabelText('Entry price'), '210')
    await user.click(screen.getByRole('button', { name: 'Add position' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))

    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Quantity'), '5')
    await user.type(screen.getByLabelText('Entry price'), '220')
    await user.click(screen.getByRole('button', { name: 'Add position' }))
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(2))

    expect(mockedPortfolioApi.buy).toHaveBeenCalledTimes(2)
    expect(mockedPortfolioApi.buy).toHaveBeenNthCalledWith(1, 7, { symbol: 'AAPL', quantity: 10, price: 210 })
    expect(mockedPortfolioApi.buy).toHaveBeenNthCalledWith(2, 7, { symbol: 'AAPL', quantity: 5, price: 220 })
  })

  it('calls onClose when Cancel is clicked, without calling the API', async () => {
    const user = userEvent.setup()
    const { onClose } = renderDialog()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
    expect(mockedPortfolioApi.buy).not.toHaveBeenCalled()
  })
})
