import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LearningOverview } from './LearningOverview'
import { dashboardApi } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  dashboardApi: { learning: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LearningOverview />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const learningView = {
  engine_rankings: [
    { engine_name: 'Technical', engine_version: '1.4.0', accuracy: 0.62, current_weight: 0.45, rank: 1 },
    { engine_name: 'News', engine_version: '1.0.0', accuracy: 0.51, current_weight: 0.2, rank: 2 },
  ],
  recent_samples: [],
  promotion_candidates: [],
  drift_alerts: [],
  calibration_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LearningOverview', () => {
  it('shows an honest unavailable state without manufacturing a trend', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce({ ...learningView, engine_rankings: [] })
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No rankings yet')).toBeInTheDocument())
  })

  it('renders the real engine ranking chart once data loads, not the empty state', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce(learningView)
    renderWithClient()
    await waitFor(() => expect(screen.getByLabelText('Engine accuracy ranking')).toBeInTheDocument())
    expect(screen.queryByText('No rankings yet')).not.toBeInTheDocument()
  })

  it('links to the full Learning page', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce(learningView)
    renderWithClient()
    await waitFor(() => expect(screen.getByRole('link', { name: /View all/ })).toHaveAttribute('href', '/learning'))
  })
})
