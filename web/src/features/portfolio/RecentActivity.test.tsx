import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RecentActivity } from './RecentActivity'
import { portfolioApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  portfolioApi: { transactions: vi.fn() },
}))

const mockedPortfolioApi = vi.mocked(portfolioApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RecentActivity portfolioId={1} />
    </QueryClientProvider>,
  )
}

const transactions = [
  {
    id: 1,
    portfolio_id: 1,
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
  },
  {
    id: 2,
    portfolio_id: 1,
    transaction_type: 'buy' as const,
    symbol: 'AAPL',
    quantity: 10,
    price: 150,
    amount: 1500,
    fee: 1,
    tax: 0,
    currency: 'USD',
    executed_at: '2026-02-01T00:00:00Z',
    notes: '',
    created_at: '2026-02-01T00:00:00Z',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RecentActivity', () => {
  it('shows an honest empty state when there is no transaction history', async () => {
    mockedPortfolioApi.transactions.mockResolvedValueOnce([])
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No activity yet')).toBeInTheDocument())
  })

  it('renders real transactions sorted newest-first, never a fabricated ledger', async () => {
    mockedPortfolioApi.transactions.mockResolvedValueOnce(transactions)
    renderWithClient()
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('buy')
    expect(rows[1]).toHaveTextContent('deposit')
  })

  it('shows a retryable error state when the request fails', async () => {
    mockedPortfolioApi.transactions.mockRejectedValueOnce(new Error('network down'))
    renderWithClient()
    await waitFor(() => expect(screen.getByText("Couldn't load this data")).toBeInTheDocument())
  })
})
