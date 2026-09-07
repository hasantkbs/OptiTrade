import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AlertsOverview } from './AlertsOverview'
import { alertsApi, dashboardApi } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  dashboardApi: { alerts: vi.fn() },
  alertsApi: { list: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)
const mockedAlertsApi = vi.mocked(alertsApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AlertsOverview />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const alertDashboard = {
  active_alerts: 4,
  fired_last_24h: 2,
  recently_fired: [{ alert_id: 1, symbol: 'AAPL', message: 'Price crossed threshold', triggered_at: '2026-01-01T12:00:00Z' }],
  trigger_frequency_by_type: { price: 2 },
  generated_at: '2026-01-01T00:00:00Z',
}

const alerts = [
  {
    id: 1,
    owner: 'user-1',
    watchlist_id: 1,
    symbol: 'AAPL',
    portfolio_id: null,
    category: 'price' as const,
    alert_type: 'price_above',
    parameters: { threshold: 200 },
    cooldown_minutes: 60,
    enabled: true,
    last_state: null,
    last_checked_at: null,
    last_triggered_at: '2026-01-01T12:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AlertsOverview', () => {
  it('shows an honest empty state when nothing has fired', async () => {
    mockedDashboardApi.alerts.mockResolvedValueOnce({ ...alertDashboard, recently_fired: [] })
    mockedAlertsApi.list.mockResolvedValueOnce([])
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No alerts fired recently')).toBeInTheDocument())
  })

  it('renders real threshold parameters and enabled state, never an invented severity', async () => {
    mockedDashboardApi.alerts.mockResolvedValueOnce(alertDashboard)
    mockedAlertsApi.list.mockResolvedValueOnce(alerts)
    renderWithClient()
    await waitFor(() => expect(screen.getByText('Price crossed threshold')).toBeInTheDocument())
    expect(screen.getByText('threshold: 200')).toBeInTheDocument()
    expect(screen.getByText('Enabled')).toBeInTheDocument()
    expect(screen.queryByText(/critical|warning|info/i)).not.toBeInTheDocument()
  })

  it('links to the full Alerts page', async () => {
    mockedDashboardApi.alerts.mockResolvedValueOnce(alertDashboard)
    mockedAlertsApi.list.mockResolvedValueOnce(alerts)
    renderWithClient()
    await waitFor(() => expect(screen.getByRole('link', { name: /View all/ })).toHaveAttribute('href', '/alerts'))
  })
})
