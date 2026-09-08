import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EngineAccuracyPanel } from './EngineAccuracyPanel'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { engines: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <EngineAccuracyPanel />
    </QueryClientProvider>,
  )
}

function metrics(window: '7d' | '30d', accuracy: number, sampleCount: number) {
  return {
    engine_name: 'TechnicalEngine',
    engine_version: '1.0.0',
    window,
    sample_count: sampleCount,
    accuracy,
    precision: 0.6,
    recall: 0.55,
    calibration_error: 0.08,
    confidence_reliability: 0.92,
    expected_return_error: 0.015,
    volatility_error: 0.02,
    computed_at: '2026-01-01T00:00:00Z',
  }
}

const engineView = {
  engines: [
    {
      engine_name: 'TechnicalEngine',
      engine_version: '1.0.0',
      accuracy_by_window: { '7d': metrics('7d', 0.7, 40), '30d': metrics('30d', 0.62, 200) },
      current_weight: 0.4,
      latest_drift: null,
    },
    { engine_name: 'NewsEngine', engine_version: '1.0.0', accuracy_by_window: {}, current_weight: null, latest_drift: null },
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

describe('EngineAccuracyPanel', () => {
  it('shows an honest empty state before any engine has reported', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce({ ...engineView, engines: [] })
    renderPanel()
    await waitFor(() => expect(screen.getByText('No engines reporting yet')).toBeInTheDocument())
  })

  it('shows an honest per-engine unavailable note when an engine has no evaluated window yet', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('No evaluated samples for any rolling window yet.')).toBeInTheDocument())
  })

  it('renders real accuracy/precision/recall/ECE/MAE for the default window, and switches windows on tab click', async () => {
    const user = userEvent.setup()
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderPanel()
    await waitFor(() => expect(screen.getByText('70.0%')).toBeInTheDocument())
    expect(screen.getByText('60.0%')).toBeInTheDocument()
    expect(screen.getByText('55.0%')).toBeInTheDocument()
    expect(screen.getByText('0.080')).toBeInTheDocument()
    expect(screen.getByText('40 evaluated samples in this window')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: '30D' }))
    await waitFor(() => expect(screen.getByText('62.0%')).toBeInTheDocument())
    expect(screen.getByText('200 evaluated samples in this window')).toBeInTheDocument()
  })
})
