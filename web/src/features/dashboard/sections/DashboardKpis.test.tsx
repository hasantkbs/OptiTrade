import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DashboardKpis } from './DashboardKpis'
import { dashboardApi, portfolioApi } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  dashboardApi: { overview: vi.fn(), portfolio: vi.fn() },
  portfolioApi: { list: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)
const mockedPortfolioApi = vi.mocked(portfolioApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DashboardKpis />
    </QueryClientProvider>,
  )
}

const overview = {
  total_users: 10,
  active_users: 4,
  total_portfolios: 1,
  total_watchlists: 7,
  total_alerts: 5,
  total_paper_accounts: 1,
  total_models: 6,
  active_engines: 9,
  learning_status: { engines_tracked: 3, total_samples: 100, pending_samples: 2, last_evaluated_at: null },
  generated_at: '2026-01-01T00:00:00Z',
}

const portfolio = { id: 1, owner: 'user-1', name: 'Core', base_currency: 'USD', created_at: '2026-01-01T00:00:00Z' }

const portfolioDashboard = {
  dashboard: {
    portfolio_id: 1,
    as_of: '2026-01-01T00:00:00Z',
    cash_balance: 1000,
    total_value: 25000,
    realized_pnl: 500,
    unrealized_pnl: 1200,
    positions: [],
    allocation: { by_symbol_pct: {}, by_sector_pct: {}, by_country_pct: {}, by_currency_pct: {}, cash_weight_pct: 4 },
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

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DashboardKpis critical rendering states', () => {
  it('shows KPI labels immediately while loading, before any value renders', () => {
    mockedDashboardApi.overview.mockImplementation(() => new Promise(() => {}))
    mockedPortfolioApi.list.mockImplementation(() => new Promise(() => {}))
    renderWithClient()
    expect(screen.getByText('Portfolio value')).toBeInTheDocument()
    expect(screen.getByText('Active alerts')).toBeInTheDocument()
    expect(screen.queryByText('$25,000')).not.toBeInTheDocument()
  })

  it('renders real values from the backend once loaded - never fabricated', async () => {
    mockedDashboardApi.overview.mockResolvedValueOnce(overview)
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolio])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(portfolioDashboard)
    renderWithClient()
    await waitFor(() => expect(screen.getByText('$25,000')).toBeInTheDocument())
    expect(screen.getByText('$1,200')).toBeInTheDocument()
    expect(screen.getByText('8.5%')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
  })

  it('shows an honest unavailable state for portfolio-derived KPIs when no portfolio exists', async () => {
    mockedDashboardApi.overview.mockResolvedValueOnce({ ...overview, total_portfolios: 0 })
    mockedPortfolioApi.list.mockResolvedValueOnce([])
    renderWithClient()
    await waitFor(() => expect(screen.getAllByText('No portfolio yet').length).toBeGreaterThan(0))
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3)
  })

  it('shows a retryable error state when the overview request fails', async () => {
    mockedDashboardApi.overview.mockRejectedValueOnce(new Error('network down'))
    mockedPortfolioApi.list.mockResolvedValueOnce([])
    renderWithClient()
    await waitFor(() => expect(screen.getByText("Couldn't load this data")).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
