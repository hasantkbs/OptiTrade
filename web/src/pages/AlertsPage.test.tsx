import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AlertsPage } from './AlertsPage'
import { alertsApi, portfolioApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  alertsApi: { list: vi.fn(), create: vi.fn(), setEnabled: vi.fn(), remove: vi.fn(), scan: vi.fn() },
  portfolioApi: { list: vi.fn() },
}))

const mockedAlertsApi = vi.mocked(alertsApi)
const mockedPortfolioApi = vi.mocked(portfolioApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AlertsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const alert = {
  id: 1,
  owner: 'user-1',
  watchlist_id: null,
  symbol: 'AAPL',
  portfolio_id: null,
  category: 'price' as const,
  alert_type: 'price_above' as const,
  parameters: { threshold: 200 },
  cooldown_minutes: 60,
  enabled: true,
  last_state: {},
  last_checked_at: null,
  last_triggered_at: null,
  created_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedPortfolioApi.list.mockResolvedValue([])
})

describe('AlertsPage', () => {
  it('shows a loading skeleton, then the real alerts once loaded', async () => {
    mockedAlertsApi.list.mockResolvedValueOnce([alert])
    renderPage()
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Alerts' })).toBeInTheDocument()
    expect(screen.getByText('Total alerts')).toBeInTheDocument()
  })

  it('shows a retryable error state when the alert list fails to load', async () => {
    mockedAlertsApi.list.mockRejectedValueOnce(new Error('down'))
    renderPage()
    await waitFor(() => expect(screen.getByText("Couldn't load this data")).toBeInTheDocument())
  })

  it('assembles the summary, list, create form and scan panel together', async () => {
    mockedAlertsApi.list.mockResolvedValueOnce([alert])
    renderPage()
    await waitFor(() => expect(screen.getByText('Your alerts')).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Create alert' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Scan alerts' })).toBeInTheDocument()
  })

  it('Refresh invalidates the alerts query', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.list.mockResolvedValue([alert])
    renderPage()
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())
    const callsBefore = mockedAlertsApi.list.mock.calls.length
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(mockedAlertsApi.list.mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
