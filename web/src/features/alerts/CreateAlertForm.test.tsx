import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CreateAlertForm } from './CreateAlertForm'
import { alertsApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  alertsApi: { create: vi.fn() },
}))

const mockedAlertsApi = vi.mocked(alertsApi)

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CreateAlertForm />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CreateAlertForm', () => {
  it('defaults to a Price/Price Above alert requiring a symbol and threshold', () => {
    renderForm()
    expect(screen.getByLabelText('Category')).toHaveValue('price')
    expect(screen.getByLabelText('Alert type')).toHaveValue('price_above')
    expect(screen.getByLabelText('Symbol')).toBeInTheDocument()
    expect(screen.getByLabelText('Threshold price')).toBeInTheDocument()
  })

  it('rejects submission with no symbol and no threshold, never calling the backend', async () => {
    const user = userEvent.setup()
    renderForm()
    await user.click(screen.getByRole('button', { name: 'Create alert' }))
    expect(screen.getByText('Symbol is required for this alert type.')).toBeInTheDocument()
    expect(screen.getByText('Threshold price is required.')).toBeInTheDocument()
    expect(mockedAlertsApi.create).not.toHaveBeenCalled()
  })

  it('rejects a non-numeric threshold', async () => {
    const user = userEvent.setup()
    renderForm()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Threshold price'), 'not-a-number')
    await user.click(screen.getByRole('button', { name: 'Create alert' }))
    expect(screen.getByText('Threshold price must be a number.')).toBeInTheDocument()
    expect(mockedAlertsApi.create).not.toHaveBeenCalled()
  })

  it('creates a real CreateAlertRequest matching the backend schema exactly on valid input', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.create.mockResolvedValueOnce({
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
    })
    renderForm()
    await user.type(screen.getByLabelText('Symbol'), 'aapl')
    await user.type(screen.getByLabelText('Threshold price'), '200')
    await user.click(screen.getByRole('button', { name: 'Create alert' }))

    await waitFor(() => expect(screen.getByText('Alert created.')).toBeInTheDocument())
    expect(mockedAlertsApi.create).toHaveBeenCalledWith({
      category: 'price',
      alert_type: 'price_above',
      parameters: { threshold: 200 },
      symbol: 'AAPL',
    })
  })

  it('shows the real backend error on a failed creation', async () => {
    const user = userEvent.setup()
    mockedAlertsApi.create.mockRejectedValueOnce(new Error('rejected'))
    renderForm()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.type(screen.getByLabelText('Threshold price'), '200')
    await user.click(screen.getByRole('button', { name: 'Create alert' }))
    await waitFor(() => expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument())
  })

  it('a parameterless alert type (e.g. Decision: BUY appears) shows no parameter fields', async () => {
    const user = userEvent.setup()
    renderForm()
    await user.selectOptions(screen.getByLabelText('Category'), 'decision')
    await user.selectOptions(screen.getByLabelText('Alert type'), 'decision_buy')
    expect(screen.getByText('This alert type takes no additional parameters.')).toBeInTheDocument()
  })
})
