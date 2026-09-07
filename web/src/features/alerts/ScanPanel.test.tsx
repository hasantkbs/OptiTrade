import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ScanPanel } from './ScanPanel'
import { alertsApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  alertsApi: { scan: vi.fn() },
}))

const mockedAlertsApi = vi.mocked(alertsApi)

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScanPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const scanReportNoTriggers = {
  started_at: '2026-01-01T12:00:00Z',
  total_alerts: 3,
  checked_count: 3,
  triggered_count: 0,
  outcomes: [
    { alert_id: 1, status: 'not_triggered' as const, duration_ms: 120, attempts: 1, error_type: null, trigger_event: null },
    { alert_id: 2, status: 'skipped_cooldown' as const, duration_ms: 5, attempts: 1, error_type: null, trigger_event: null },
    { alert_id: 3, status: 'failed' as const, duration_ms: 50, attempts: 1, error_type: 'InsufficientAlertDataError', trigger_event: null },
  ],
}

const scanReportTriggered = {
  ...scanReportNoTriggers,
  triggered_count: 1,
  outcomes: [
    {
      alert_id: 4,
      status: 'triggered' as const,
      duration_ms: 80,
      attempts: 1,
      error_type: null,
      trigger_event: {
        alert_id: 4,
        owner: 'user-1',
        symbol: 'AAPL',
        portfolio_id: null,
        category: 'price' as const,
        alert_type: 'price_above' as const,
        severity: 'warning' as const,
        message: 'AAPL price 210.00 is above 200.00',
        evidence: { price: 210, threshold: 200 },
        related_decision: null,
        triggered_at: '2026-01-01T12:00:05Z',
      },
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ScanPanel', () => {
  it('prompts the user to scan and clarifies there is no push notification system', () => {
    renderPanel()
    expect(screen.getByText(/does not send push notifications/)).toBeInTheDocument()
  })

  it('runs a real scan and shows the exact summary counts returned, never a fabricated one', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.scan.mockResolvedValueOnce(scanReportNoTriggers)
    renderPanel()
    await user.click(screen.getByRole('button', { name: 'Scan now' }))
    await waitFor(() => expect(screen.getByText('3 / 3')).toBeInTheDocument())
    expect(screen.getByText('failed: 1')).toBeInTheDocument()
    expect(screen.getByText('skipped cooldown: 1')).toBeInTheDocument()
  })

  it('shows a real triggered result prominently with severity, message and evidence, linking the symbol', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.scan.mockResolvedValueOnce(scanReportTriggered)
    renderPanel()
    await user.click(screen.getByRole('button', { name: 'Scan now' }))
    await waitFor(() => expect(screen.getByText('AAPL price 210.00 is above 200.00')).toBeInTheDocument())
    expect(screen.getByText('warning')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'AAPL' })).toHaveAttribute('href', '/assets/AAPL')
    expect(screen.getByText(/price: 210.00/)).toBeInTheDocument()
  })

  it('shows a retryable error state when the scan request fails', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.scan.mockRejectedValueOnce(new Error('rate limited'))
    renderPanel()
    await user.click(screen.getByRole('button', { name: 'Scan now' }))
    await waitFor(() => expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument())
  })

  it('disables the scan button while a scan is already running, preventing a duplicate call', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.scan.mockImplementation(() => new Promise(() => {}))
    renderPanel()
    await user.click(screen.getByRole('button', { name: 'Scan now' }))
    expect(mockedAlertsApi.scan).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button'))
    expect(mockedAlertsApi.scan).toHaveBeenCalledTimes(1)
  })
})
