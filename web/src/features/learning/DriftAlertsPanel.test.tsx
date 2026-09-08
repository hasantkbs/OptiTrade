import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DriftAlertsPanel } from './DriftAlertsPanel'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { engines: vi.fn(), learning: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DriftAlertsPanel />
    </QueryClientProvider>,
  )
}

const driftSignal = {
  engine_name: 'NewsEngine',
  engine_version: '1.0.0',
  drift_type: 'degrading' as const,
  magnitude: 0.24,
  recent_window: '7d' as const,
  baseline_window: '30d' as const,
  evidence: 'Accuracy dropped 12pp vs baseline',
  detected_at: '2026-01-01T00:00:00Z',
}

const learningView = {
  engine_rankings: [],
  recent_samples: [],
  promotion_candidates: [],
  drift_alerts: [driftSignal],
  calibration_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

const engineView = {
  engines: [
    { engine_name: 'TechnicalEngine', engine_version: '1.0.0', accuracy_by_window: {}, current_weight: 0.4, latest_drift: { ...driftSignal, engine_name: 'TechnicalEngine', drift_type: 'stable' as const } },
    { engine_name: 'FundamentalEngine', engine_version: '1.0.0', accuracy_by_window: {}, current_weight: 0.3, latest_drift: null },
  ],
  calibration: [],
  drift_signals: [],
  confidence_history: [],
  regime_distribution: {},
  expected_return_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DriftAlertsPanel', () => {
  it('shows an honest empty state when nothing is currently flagged', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce({ ...learningView, drift_alerts: [] })
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('No active drift alerts')).toBeInTheDocument())
  })

  it('renders real active drift alerts with evidence and window comparison', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce(learningView)
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('degrading')).toBeInTheDocument())
    expect(screen.getByText('Accuracy dropped 12pp vs baseline')).toBeInTheDocument()
  })

  it('distinguishes "stable" (a real signal) from "No drift signal yet" (genuinely unavailable)', async () => {
    mockedDashboardApi.learning.mockResolvedValueOnce(learningView)
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('stable')).toBeInTheDocument())
    expect(screen.getByText('No drift signal yet')).toBeInTheDocument()
  })
})
