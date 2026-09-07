import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SystemEngineStatus } from './SystemEngineStatus'
import { dashboardApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  dashboardApi: { engines: vi.fn() },
}))

const mockedDashboardApi = vi.mocked(dashboardApi)

function renderStatus() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SystemEngineStatus />
    </QueryClientProvider>,
  )
}

const engineView = {
  engines: [
    { engine_name: 'TechnicalEngine', engine_version: '1.0.0', accuracy_by_window: {}, current_weight: 0.45, latest_drift: { engine_name: 'TechnicalEngine', engine_version: '1.0.0', drift_type: 'stable' as const, magnitude: 0.01, recent_window: '7d' as const, baseline_window: '30d' as const, evidence: 'ok', detected_at: '2026-01-01T00:00:00Z' } },
    { engine_name: 'NewsEngine', engine_version: '1.0.0', accuracy_by_window: {}, current_weight: null, latest_drift: null },
  ],
  calibration: [],
  drift_signals: [],
  confidence_history: [],
  regime_distribution: {},
  expected_return_history: [],
  generated_at: '2026-01-01T12:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SystemEngineStatus', () => {
  it('shows an honest empty state when no engines are reporting', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce({ ...engineView, engines: [] })
    renderStatus()
    await waitFor(() => expect(screen.getByText('No engines reporting yet')).toBeInTheDocument())
  })

  it('renders real per-engine weight and drift, and an honest "unavailable" note when either is missing', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce(engineView)
    renderStatus()
    await waitFor(() => expect(screen.getByText('TechnicalEngine')).toBeInTheDocument())
    expect(screen.getByText('45%')).toBeInTheDocument()
    expect(screen.getByText('stable')).toBeInTheDocument()
    expect(screen.getByText('Weight unavailable')).toBeInTheDocument()
    expect(screen.getByText('No drift signal')).toBeInTheDocument()
  })

  it('shows a retryable error state on failure', async () => {
    mockedDashboardApi.engines.mockRejectedValueOnce(new Error('down'))
    renderStatus()
    await waitFor(() => expect(screen.getByText("Couldn't load this data")).toBeInTheDocument())
  })
})
