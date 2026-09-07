import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PortfolioPerformance } from './PortfolioPerformance'
import { dashboardApi, portfolioApi } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  dashboardApi: { portfolio: vi.fn() },
  portfolioApi: { list: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)
const mockedPortfolioApi = vi.mocked(portfolioApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PortfolioPerformance />
    </QueryClientProvider>,
  )
}

const portfolioA = { id: 1, owner: 'user-1', name: 'Core', base_currency: 'USD', created_at: '2026-01-01T00:00:00Z' }
const portfolioB = { id: 2, owner: 'user-1', name: 'Satellite', base_currency: 'USD', created_at: '2026-01-01T00:00:00Z' }

function dashboardFor(portfolioId: number) {
  return {
    dashboard: {
      portfolio_id: portfolioId,
      as_of: '2026-01-01T00:00:00Z',
      cash_balance: 1000,
      total_value: 25000,
      realized_pnl: 500,
      unrealized_pnl: 1200,
      positions: [],
      allocation: {
        by_symbol_pct: { AAPL: 40, MSFT: 30, GOOG: 26 },
        by_sector_pct: { Technology: 96 },
        by_country_pct: {},
        by_currency_pct: {},
        cash_weight_pct: 4,
      },
      risk: {
        volatility_pct: 12,
        beta: 1.1,
        correlation_matrix: {},
        diversification_score: 0.6,
        var_95_pct: 3,
        cvar_95_pct: 4,
        max_drawdown_pct: 8.5,
        expected_drawdown_pct: 5,
        downside_risk_pct: 6,
        concentration_risk: 0.2,
      },
      recommendations: [],
    },
    sharpe_ratio: 1.2,
    generated_at: '2026-01-01T00:00:00Z',
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PortfolioPerformance', () => {
  it('shows an honest empty state when no portfolio exists', async () => {
    mockedPortfolioApi.list.mockResolvedValueOnce([])
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No portfolio yet')).toBeInTheDocument())
  })

  it('renders real allocation and risk scalars for the current portfolio, never a fabricated equity curve', async () => {
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(dashboardFor(1))
    renderWithClient()
    await waitFor(() => expect(screen.getByLabelText('Portfolio allocation by symbol')).toBeInTheDocument())
    expect(screen.getByText('4.0%')).toBeInTheDocument()
    expect(screen.getByText('1.10')).toBeInTheDocument()
    expect(screen.queryByText(/equity curve/i)).not.toBeInTheDocument()
  })

  it('switches the allocation chart view between symbol and sector breakdowns', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(dashboardFor(1))
    renderWithClient()
    await waitFor(() => expect(screen.getByLabelText('Portfolio allocation by symbol')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: 'By sector' }))
    await waitFor(() => expect(screen.getByLabelText('Portfolio allocation by sector')).toBeInTheDocument())
  })

  it('does not show a portfolio selector when only one portfolio exists', async () => {
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(dashboardFor(1))
    renderWithClient()
    await waitFor(() => expect(screen.getByText('Core')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /▾/ })).not.toBeInTheDocument()
  })

  it('switches to the selected portfolio via the selector when multiple portfolios exist', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.list.mockResolvedValue([portfolioA, portfolioB])
    mockedDashboardApi.portfolio.mockImplementation((id: number) => Promise.resolve(dashboardFor(id)))
    renderWithClient()

    await waitFor(() => expect(screen.getByRole('button', { name: /Core ▾/ })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /Core ▾/ }))
    await user.click(screen.getByRole('menuitem', { name: 'Satellite' }))

    await waitFor(() => expect(screen.getByRole('button', { name: /Satellite ▾/ })).toBeInTheDocument())
  })
})
