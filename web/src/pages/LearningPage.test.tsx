import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LearningPage } from './LearningPage'
import { dashboardApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  dashboardApi: { overview: vi.fn(), engines: vi.fn(), learning: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LearningPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const overview = {
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
}

const emptyEngineView = {
  engines: [],
  calibration: [],
  drift_signals: [],
  confidence_history: [],
  regime_distribution: {},
  expected_return_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

const learningView = {
  engine_rankings: [{ engine_name: 'TechnicalEngine', engine_version: '1.0.0', accuracy: 0.62, current_weight: 0.4, rank: 1 }],
  recent_samples: [],
  promotion_candidates: [],
  drift_alerts: [],
  calibration_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedDashboardApi.overview.mockResolvedValue(overview)
  mockedDashboardApi.engines.mockResolvedValue(emptyEngineView)
})

describe('LearningPage', () => {
  it('renders the header and status panel with real data', async () => {
    mockedDashboardApi.learning.mockResolvedValue(learningView)
    renderPage()
    expect(screen.getByRole('heading', { name: 'Continuous Learning' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('500')).toBeInTheDocument())
  })

  it('shows the engine ranking table once loaded', async () => {
    mockedDashboardApi.learning.mockResolvedValue(learningView)
    renderPage()
    await waitFor(() => expect(screen.getByText('62.0%')).toBeInTheDocument())
    expect(screen.getByText('0.400')).toBeInTheDocument()
  })

  it('shows an honest empty state for the ranking table when there are no rankings yet', async () => {
    mockedDashboardApi.learning.mockResolvedValue({ ...learningView, engine_rankings: [] })
    renderPage()
    await waitFor(() => expect(screen.getByText('No engine rankings yet')).toBeInTheDocument())
  })

  it('shows a retryable error state when the learning resource fails, across every section that depends on it', async () => {
    mockedDashboardApi.learning.mockRejectedValue(new Error('down'))
    renderPage()
    // A single failed GET /dashboard/learning fetch is shared (same
    // query key) by the ranking table and every learning panel below
    // it, so the same honest error legitimately appears more than once.
    await waitFor(() => expect(screen.getAllByText("Couldn't load this data").length).toBeGreaterThan(0))
  })

  it('links to Decision Intelligence for symbol-level analysis', async () => {
    mockedDashboardApi.learning.mockResolvedValue(learningView)
    renderPage()
    expect(screen.getByRole('link', { name: /Analyze a symbol/ })).toHaveAttribute('href', '/decisions')
  })

  it('Refresh invalidates the underlying dashboard queries', async () => {
    const user = userEvent.setup()
    mockedDashboardApi.learning.mockResolvedValue(learningView)
    renderPage()
    await waitFor(() => expect(screen.getByText('62.0%')).toBeInTheDocument())
    const callsBefore = mockedDashboardApi.learning.mock.calls.length
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(mockedDashboardApi.learning.mock.calls.length).toBeGreaterThan(callsBefore))
  })
})
