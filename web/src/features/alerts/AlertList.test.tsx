import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AlertList } from './AlertList'
import { alertsApi } from '../../api/endpoints'
import type { Alert } from '../../api/types'

vi.mock('../../api/endpoints', () => ({
  alertsApi: { setEnabled: vi.fn(), remove: vi.fn() },
}))

const mockedAlertsApi = vi.mocked(alertsApi)

function renderList(alerts: Alert[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AlertList alerts={alerts} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const priceAlert: Alert = {
  id: 1,
  owner: 'user-1',
  watchlist_id: null,
  symbol: 'AAPL',
  portfolio_id: null,
  category: 'price',
  alert_type: 'price_above',
  parameters: { threshold: 200 },
  cooldown_minutes: 60,
  enabled: true,
  last_state: {},
  last_checked_at: null,
  last_triggered_at: null,
  created_at: '2026-01-01T00:00:00Z',
}

const decisionAlert: Alert = {
  ...priceAlert,
  id: 2,
  category: 'decision',
  alert_type: 'decision_buy',
  parameters: {},
  last_triggered_at: '2026-02-01T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AlertList', () => {
  it('shows an honest empty state with no alerts', () => {
    renderList([])
    expect(screen.getByText('No alerts configured')).toBeInTheDocument()
  })

  it('shows real fields only - friendly type label, parameters, never fabricated severity/status', () => {
    renderList([priceAlert])
    expect(screen.getByText('Price Above')).toBeInTheDocument()
    expect(screen.getByText('threshold: 200')).toBeInTheDocument()
    expect(screen.getByText('Never')).toBeInTheDocument()
    expect(screen.queryByText(/severity|critical|warning/i)).not.toBeInTheDocument()
  })

  it('links the symbol to the Asset Explorer', () => {
    renderList([priceAlert])
    expect(screen.getByRole('link', { name: 'AAPL' })).toHaveAttribute('href', '/assets/AAPL')
  })

  it('links a decision-category alert to Decision Intelligence', () => {
    renderList([decisionAlert])
    expect(screen.getByRole('link', { name: /View decision/ })).toHaveAttribute('href', '/decisions')
    expect(screen.getByText('2/1/2026, 12:00:00 AM')).toBeInTheDocument()
  })

  it('toggles enabled state via the real PATCH endpoint', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.setEnabled.mockResolvedValueOnce({ ...priceAlert, enabled: false })
    renderList([priceAlert])
    await user.click(screen.getByRole('button', { name: 'Disable' }))
    expect(mockedAlertsApi.setEnabled).toHaveBeenCalledWith(1, false)
  })

  it('shows a mutation error when enabling/disabling fails', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.setEnabled.mockRejectedValueOnce(new Error('failed'))
    renderList([priceAlert])
    await user.click(screen.getByRole('button', { name: 'Disable' }))
    await waitFor(() => expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument())
  })

  it('requires confirmation before deleting, and only deletes after confirming', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.remove.mockResolvedValueOnce({ status: 'deleted' })
    renderList([priceAlert])
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(mockedAlertsApi.remove).not.toHaveBeenCalled()
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(mockedAlertsApi.remove).toHaveBeenCalledWith(1))
  })

  it('cancelling the delete confirmation never calls the backend', async () => {
    const user = userEvent.setup()
    renderList([priceAlert])
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(mockedAlertsApi.remove).not.toHaveBeenCalled()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('shows a mutation error when deletion fails', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.remove.mockRejectedValueOnce(new Error('failed'))
    renderList([priceAlert])
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    const dialog = screen.getByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument())
  })
})
