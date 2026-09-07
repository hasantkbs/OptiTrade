import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { KpiCardsSection } from './KpiCardsSection'
import { dashboardApi } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  dashboardApi: { overview: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <KpiCardsSection />
    </QueryClientProvider>,
  )
}

const overview = {
  total_users: 10,
  active_users: 4,
  total_portfolios: 3,
  total_watchlists: 7,
  total_alerts: 5,
  total_paper_accounts: 1,
  total_models: 6,
  active_engines: 9,
  learning_status: { engines_tracked: 3, total_samples: 100, pending_samples: 2, last_evaluated_at: null },
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('KpiCardsSection critical rendering states', () => {
  it('shows the KPI labels immediately while data is loading', () => {
    mockedDashboardApi.overview.mockImplementation(() => new Promise(() => {}))
    renderWithClient()
    expect(screen.getByText('Total portfolios')).toBeInTheDocument()
    expect(screen.getByText('Active alerts')).toBeInTheDocument()
    // The real value hasn't arrived yet - only labels + skeleton placeholders.
    expect(screen.queryByText('3')).not.toBeInTheDocument()
  })

  it('renders real values from the backend once loaded - never fabricated', async () => {
    mockedDashboardApi.overview.mockResolvedValueOnce(overview)
    renderWithClient()
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument())
    expect(screen.getByText('7')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('9')).toBeInTheDocument()
  })

  it('shows a retryable error state when the request fails', async () => {
    mockedDashboardApi.overview.mockRejectedValueOnce(new Error('network down'))
    renderWithClient()
    await waitFor(() => expect(screen.getByText("Couldn't load this data")).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})
