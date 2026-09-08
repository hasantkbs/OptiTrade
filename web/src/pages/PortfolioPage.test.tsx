import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PortfolioPage } from './PortfolioPage'
import { dashboardApi, portfolioApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  dashboardApi: { portfolio: vi.fn() },
  portfolioApi: { list: vi.fn(), transactions: vi.fn(), create: vi.fn(), buy: vi.fn(), deposit: vi.fn() },
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
    expect(screen.getByRole('button', { name: 'Create portfolio' })).toBeInTheDocument()
  })

  it('creates a portfolio from the empty state and shows it without a manual refresh', async () => {
    const user = userEvent.setup()
    // A stateful mock (not a fixed queue of `.mockResolvedValueOnce`
    // calls) so `list` genuinely reflects the "backend" state at the
    // time of each call, including the invalidation-triggered refetch
    // after creation succeeds - this is what actually exercises "no
    // manual refresh needed", not just a hardcoded second response.
    let portfolios: typeof portfolioA[] = []
    mockedPortfolioApi.list.mockImplementation(() => Promise.resolve(portfolios))
    mockedPortfolioApi.create.mockImplementationOnce(async () => {
      portfolios = [portfolioA]
      return portfolioA
    })
    mockedDashboardApi.portfolio.mockResolvedValueOnce(extendedFor(1, 25000))
    renderPage()
    await waitFor(() => expect(screen.getByText('No portfolios yet')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Create portfolio' }))
    const dialog = screen.getByRole('dialog')
    await user.type(within(dialog).getByLabelText('Portfolio name'), 'Core')
    await user.click(within(dialog).getByRole('button', { name: 'Create portfolio' }))

    await waitFor(() => expect(mockedPortfolioApi.create).toHaveBeenCalledWith({ name: 'Core' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core' })).toBeInTheDocument())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
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

  it('offers an obvious Add position action that opens the Add Position dialog', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(extendedFor(1, 25000))
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '+ Add position' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Add position' })).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Symbol')).toBeInTheDocument()
    // Preserved existing actions, per scope control.
    expect(screen.getByRole('button', { name: 'New portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })

  it('offers an obvious Add cash action that opens the Add Cash dialog, alongside every other preserved action', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.list.mockResolvedValueOnce([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValueOnce(extendedFor(1, 25000))
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '+ Add cash' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Add cash' })).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Amount')).toBeInTheDocument()
    // Preserved existing actions, per scope control.
    expect(screen.getByRole('button', { name: '+ Add position' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
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

  it('offers a way to create another portfolio once one already exists', async () => {
    const user = userEvent.setup()
    mockedPortfolioApi.list.mockResolvedValue([portfolioA])
    mockedDashboardApi.portfolio.mockResolvedValue(extendedFor(1, 25000))
    renderPage()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Core' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'New portfolio' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
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
