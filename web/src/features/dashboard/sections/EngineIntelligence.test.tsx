import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EngineIntelligence } from './EngineIntelligence'
import { dashboardApi } from '../../../api/endpoints'

vi.mock('../../../api/endpoints', () => ({
  dashboardApi: { engines: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <EngineIntelligence />
    </QueryClientProvider>,
  )
}

const engineView = {
  engines: [
    {
      engine_name: 'Technical',
      engine_version: '1.4.0',
      accuracy_by_window: {
        '30d': {
          engine_name: 'Technical',
          engine_version: '1.4.0',
          window: '30d' as const,
          sample_count: 200,
          accuracy: 0.624,
          precision: 0.6,
          recall: 0.58,
          calibration_error: 0.05,
          confidence_reliability: 0.7,
          expected_return_error: 0.02,
          volatility_error: 0.01,
          computed_at: '2026-01-01T00:00:00Z',
        },
      },
      current_weight: 0.45,
      latest_drift: {
        engine_name: 'Technical',
        engine_version: '1.4.0',
        drift_type: 'stable' as const,
        magnitude: 0.02,
        recent_window: '7d' as const,
        baseline_window: '30d' as const,
        evidence: 'accuracy within tolerance',
        detected_at: '2026-01-01T00:00:00Z',
      },
    },
  ],
  calibration: [],
  drift_signals: [],
  confidence_history: [
    { timestamp: '2026-01-01T00:00:00Z', value: 0.7 },
    { timestamp: '2026-01-02T00:00:00Z', value: 0.75 },
  ],
  regime_distribution: { bull: 12, bear: 3 },
  expected_return_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  document.documentElement.removeAttribute('data-theme')
})

afterEach(() => {
  document.documentElement.removeAttribute('data-theme')
})

describe('EngineIntelligence', () => {
  it('shows an honest empty state when no engines are reporting', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce({ ...engineView, engines: [] })
    renderWithClient()
    await waitFor(() => expect(screen.getByText('No engines reporting yet')).toBeInTheDocument())
  })

  it('separates live weight, learning accuracy and drift status - never mixing them into one number', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderWithClient()
    await waitFor(() => expect(screen.getByText('Technical')).toBeInTheDocument())
    expect(screen.getByText('45%')).toBeInTheDocument()
    expect(screen.getByText('Accuracy (30d)')).toBeInTheDocument()
    expect(screen.getByText('62.4%')).toBeInTheDocument()
    expect(screen.getByText('stable')).toBeInTheDocument()
  })

  it('renders confidence history and regime distribution from real data', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderWithClient()
    await waitFor(() => expect(screen.getByLabelText('Decision Engine confidence over time')).toBeInTheDocument())
    expect(screen.getByLabelText('Detected market regime distribution')).toBeInTheDocument()
  })

  it('renders without crashing in dark theme', async () => {
    document.documentElement.setAttribute('data-theme', 'dark')
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderWithClient()
    await waitFor(() => expect(screen.getByText('Technical')).toBeInTheDocument())
  })
})
