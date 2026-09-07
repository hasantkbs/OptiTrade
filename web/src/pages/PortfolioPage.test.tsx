import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PortfolioPage } from './PortfolioPage'
import { dashboardApi, portfolioApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  dashboardApi: { portfolio: vi.fn() },
  portfolioApi: { list: vi.fn(), transactions: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)
const mockedPortfolioApi = vi.mocked(portfolioApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/portfolio']}>
        <PortfolioPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const portfolioA = { id: 1, owner: 'user-1', name: 'Core', base_currency: 'USD', created_at: '2026-01-01T00:00:00Z' }
const portfolioB = { id: 2, owner: 'user-1', name: 'Satellite', base_currency: 'USD', created_at: '2026-01-01T00:00:00Z' }

function extendedFor(portfolioId: number, totalValue: number) {
  return {
    dashboard: {
      portfolio_id: portfolioId,
      as_of: '2026-01-01T00:00:00Z',
      cash_balance: 1000,
      total_value: totalValue,
      realized_pnl: 500,
      unrealized_pnl: 1200,
      positions: [],
      allocation: { by_symbol_pct: {}, by_sector_pct: {}, by_country_pct: {}, by_currency_pct: {}, cash_weight_pct: 4 },
      risk: null,
      recommendations: [],
    },
    sharpe_ratio: null,
    generated_at: '2026-01-01T00:00:00Z',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedPortfolioApi.transactions.mockResolvedValue([])
})

describe('PortfolioPage', () => {
  it('shows an honest empty state when the user has no portfolios', async () => {
    mockedPortfolioApi.list.mockResolvedValueOnce([])
    renderPage()
    await waitFor(() => expect(screen.getByText('No portfolios yet')).toBeInTheDocument())
  })

  it('shows a retryable error state when the portfolio list fails to load', async () => {
    mockedPortfolioApi.list.mockRejectedValueOnce(new Error('network down'))
    renderPage()
    await waitFor(() => expect(screen.getByText("Couldn't load this data")).toBeInTheDocument())
  })

  it('loads the first portfolio by default and renders its real dashboard data', async () => {
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(extendedFor(1, 25000))
    renderPage()
    await waitFor(() => expect(screen.getByText('$25,000')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Core' })).toBeInTheDocument()
  })

  it('does not offer a portfolio selector with only one portfolio', async () => {
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(extendedFor(1, 25000))
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core' })).toBeInTheDocument())
    expect(screen.queryByText('Switch portfolio ▾')).not.toBeInTheDocument()
  })

  it('switches portfolios via the selector and never lets a slower stale response overwrite the newly selected one', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.list.mockResolvedValue([portfolioA, portfolioB])
    mockedDashboardApi.portfolio.mockImplementation((id: number) => {
      // Portfolio A's response is deliberately slower than B's, so a naive
      // "last response wins" implementation would show A's data after B is
      // selected. Query-key-per-portfolio-id means that can't happen here.
      const delay = id === 1 ? 40 : 5
      return new Promise((resolve) => setTimeout(() => resolve(extendedFor(id, id === 1 ? 25000 : 99000)), delay))
    })
    renderPage()

    await waitFor(() => expect(screen.getByText('$25,000')).toBeInTheDocument())
    await user.click(screen.getByText('Switch portfolio ▾'))
    await user.click(screen.getByRole('menuitem', { name: 'Satellite' }))

    await waitFor(() => expect(screen.getByText('$99,000')).toBeInTheDocument())
    await new Promise((resolve) => setTimeout(resolve, 60))
    expect(screen.getByText('$99,000')).toBeInTheDocument()
    expect(screen.queryByText('$25,000')).not.toBeInTheDocument()
  })

  it('invalidates and refetches the current portfolio when Refresh is clicked', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.list.mockResolvedValue([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValue(extendedFor(1, 25000))
    renderPage()
    await waitFor(() => expect(screen.getByText('$25,000')).toBeInTheDocument())

    const callsBefore = mockedDashboardApi.portfolio.mock.calls.length
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(mockedDashboardApi.portfolio.mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
