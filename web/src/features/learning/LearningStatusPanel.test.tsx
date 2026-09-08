import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LearningStatusPanel } from './LearningStatusPanel'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { overview: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LearningStatusPanel />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LearningStatusPanel', () => {
  it('renders real learning_status fields once loaded', async () => {
    mockedDashboardApi.overview.mockResolvedValueOnce({
      total_users: 1,
      active_users: 1,
      total_portfolios: 1,
      total_watchlists: 1,
      total_alerts: 1,
      total_paper_accounts: 1,
      total_models: 1,
      active_engines: 3,
      learning_status: { engines_tracked: 3, total_samples: 500, pending_samples: 12, last_evaluated_at: '2026-01-01T00:00:00Z' },
      generated_at: '2026-01-01T00:00:00Z',
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument())
    expect(screen.getByText('500')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })

  it('shows an honest "not yet evaluated" reason instead of a fake timestamp', async () => {
    mockedDashboardApi.overview.mockResolvedValueOnce({
      total_users: 1,
      active_users: 1,
      total_portfolios: 1,
      total_watchlists: 1,
      total_alerts: 1,
      total_paper_accounts: 1,
      total_models: 1,
      active_engines: 0,
      learning_status: { engines_tracked: 0, total_samples: 0, pending_samples: 0, last_evaluated_at: null },
      generated_at: '2026-01-01T00:00:00Z',
    })
    renderPanel()
    await waitFor(() => expect(screen.getByText('Not yet evaluated')).toBeInTheDocument())
  })
})
