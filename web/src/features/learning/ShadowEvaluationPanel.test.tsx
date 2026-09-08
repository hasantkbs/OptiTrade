import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ShadowEvaluationPanel } from './ShadowEvaluationPanel'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { learning: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ShadowEvaluationPanel />
    </QueryClientProvider>,
  )
}

const learningView = {
  engine_rankings: [],
  recent_samples: [
    { symbol: 'AAPL', source: 'live' as const, decision: 'BUY' as const, confidence: 0.7, decided_at: '2026-01-01T00:00:00Z', evaluated: true, correct: true },
    { symbol: 'MSFT', source: 'shadow' as const, decision: 'HOLD' as const, confidence: 0.55, decided_at: '2026-01-01T00:00:00Z', evaluated: false, correct: null },
  ],
  promotion_candidates: [],
  drift_alerts: [],
  calibration_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ShadowEvaluationPanel', () => {
  it('shows an honest empty state with no recent samples', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce({ ...learningView, recent_samples: [] })
    renderPanel()
    await waitFor(() => expect(screen.getByText('No recent samples yet')).toBeInTheDocument())
  })

  it('keeps live and shadow samples in visually separate columns, never merged', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce(learningView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('AAPL')).toBeInTheDocument())
    expect(screen.getByText('MSFT')).toBeInTheDocument()
    expect(screen.getByText('Correct')).toBeInTheDocument()
    expect(screen.getByText('Pending evaluation')).toBeInTheDocument()
    expect(screen.getByText('Production')).toBeInTheDocument()
    expect(screen.getByText('Shadow')).toBeInTheDocument()
  })
})
