import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CalibrationPanel } from './CalibrationPanel'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { engines: vi.fn(), learning: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CalibrationPanel />
    </QueryClientProvider>,
  )
}

const learningView = {
  engine_rankings: [],
  recent_samples: [],
  promotion_candidates: [],
  drift_alerts: [],
  calibration_history: [
    { engine_name: 'TechnicalEngine', engine_version: '1.0.0', window: '7d' as const, calibration_error: 0.12, confidence_reliability: 0.88, computed_at: '2026-01-01T00:00:00Z' },
    { engine_name: 'TechnicalEngine', engine_version: '1.0.0', window: '30d' as const, calibration_error: 0.09, confidence_reliability: 0.91, computed_at: '2026-01-01T00:00:00Z' },
  ],
  generated_at: '2026-01-01T00:00:00Z',
}

const engineView = {
  engines: [],
  calibration: [
    { model_id: 'model-abc', method: 'platt', calibration_error_before: 0.2, calibration_error_after: 0.08, computed_at: '2026-01-01T00:00:00Z' },
  ],
  drift_signals: [],
  confidence_history: [],
  regime_distribution: {},
  expected_return_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CalibrationPanel', () => {
  it('shows an honest empty state when there is no calibration history yet', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce({ ...learningView, calibration_history: [] })
    mockedDashboardApi.engines.mockResolvedValueOnce({ ...engineView, calibration: [] })
    renderPanel()
    await waitFor(() => expect(screen.getByText('No calibration history yet')).toBeInTheDocument())
    expect(screen.getByText('No model calibration results yet')).toBeInTheDocument()
  })

  it('renders real per-window ECE/reliability and real model before/after calibration, never generated buckets', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce(learningView)
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('0.120')).toBeInTheDocument())
    expect(screen.getByText('0.090')).toBeInTheDocument()
    expect(screen.getByText('model-abc')).toBeInTheDocument()
    expect(screen.getByText('0.200 → 0.080')).toBeInTheDocument()
    expect(screen.getByText('Improved')).toBeInTheDocument()
  })
})
