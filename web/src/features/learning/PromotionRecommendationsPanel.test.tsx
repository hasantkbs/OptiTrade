import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PromotionRecommendationsPanel } from './PromotionRecommendationsPanel'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { learning: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PromotionRecommendationsPanel />
    </QueryClientProvider>,
  )
}

const learningView = {
  engine_rankings: [],
  recent_samples: [],
  promotion_candidates: [
    { engine_name: 'TechnicalEngine', candidate_version: '2.0.0', live_version: '1.0.0', window: '30d' as const, candidate_accuracy: 0.68, live_accuracy: 0.6, candidate_sample_count: 150 },
  ],
  drift_alerts: [],
  calibration_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PromotionRecommendationsPanel', () => {
  it('shows an honest empty state with no current candidates', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce({ ...learningView, promotion_candidates: [] })
    renderPanel()
    await waitFor(() => expect(screen.getByText('No promotion candidates right now')).toBeInTheDocument())
  })

  it('renders a real candidate-vs-live comparison and the read-only disclaimer, never implying an automatic promotion', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce(learningView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('TechnicalEngine')).toBeInTheDocument())
    expect(screen.getByText('68.0%')).toBeInTheDocument()
    expect(screen.getByText('60.0%')).toBeInTheDocument()
    expect(screen.getByText('150 evaluated candidate samples')).toBeInTheDocument()
    expect(screen.getByText(/does not automatically promote, activate, or change/)).toBeInTheDocument()
  })
})
