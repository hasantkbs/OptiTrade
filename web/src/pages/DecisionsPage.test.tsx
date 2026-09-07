import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DecisionsPage } from './DecisionsPage'
import { dashboardApi, quantApi, watchlistApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  quantApi: { analyze: vi.fn() },
  watchlistApi: { list: vi.fn(), items: vi.fn() },
  dashboardApi: { engines: vi.fn() },
}))

const mockedQuantApi = vi.mocked(quantApi)
const mockedWatchlistApi = vi.mocked(watchlistApi)
const mockedDashboardApi = vi.mocked(dashboardApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DecisionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const watchlist = { id: 1, owner: 'user-1', name: 'Core', created_at: '2026-01-01T00:00:00Z' }
const watchlistItems = [
  { id: 1, watchlist_id: 1, symbol: 'AAPL', is_favorite: false, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
  { id: 2, watchlist_id: 1, symbol: 'MSFT', is_favorite: false, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
]
const engineView = {
  engines: [],
  calibration: [],
  drift_signals: [],
  confidence_history: [],
  regime_distribution: {},
  expected_return_history: [],
  generated_at: '2026-01-01T00:00:00Z',
}

function pipelineFor(symbol: string, decision: 'BUY' | 'HOLD' | 'SELL') {
  return {
    symbol,
    decision,
    confidence: 0.72,
    expected_return: 0.034,
    expected_volatility: 0.18,
    engine_breakdown: [
      {
        engine_name: 'TechnicalEngine',
        engine_version: '1.0.0',
        status: 'success' as const,
        prediction: decision,
        confidence: 0.8,
        expected_return: 0.04,
        volatility: 0.15,
        evidence: ['RSI oversold reversal'],
      },
      {
        engine_name: 'NewsEngine',
        engine_version: '1.0.0',
        status: 'failed' as const,
        prediction: null,
        confidence: null,
        expected_return: null,
        volatility: null,
        evidence: [],
      },
    ],
    evidence: ['Aggregate confidence above threshold'],
    risk: { risk_level: 'MEDIUM', expected_volatility: 0.18, data_sufficiency: 0.9 },
    explanation: 'Technical momentum outweighs neutral fundamentals.',
    metadata: {
      pipeline_version: '1.0.0',
      total_duration_ms: 120,
      stage_durations_ms: {},
      engines_available: 2,
      engines_succeeded: 1,
      degraded: true,
      timestamp: '2026-01-01T20:00:00Z',
    },
  }
}

function rateLimitError() {
  const error = new AxiosError('Too Many Requests')
  error.response = { status: 429, data: { detail: 'Rate limit exceeded, try again later.' }, statusText: 'Too Many Requests', headers: {}, config: {} as never }
  return error
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedWatchlistApi.list.mockResolvedValue([watchlist])
  mockedWatchlistApi.items.mockResolvedValue(watchlistItems)
  mockedDashboardApi.engines.mockResolvedValue(engineView)
})

describe('DecisionsPage', () => {
  it('renders the page header and an honest prompt before any symbol is chosen', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'Decision Intelligence' })).toBeInTheDocument()
    expect(screen.getByText(/Pick a symbol above/)).toBeInTheDocument()
  })

  it('always shows the honest historical-decisions unavailable state', () => {
    renderPage()
    expect(screen.getByText('Historical decision tracking is not currently exposed by the backend')).toBeInTheDocument()
  })

  it('analyzes the typed symbol exactly once via POST /quant/analyze, the same canonical path as the Asset Explorer', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'aapl')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))

    await waitFor(() => expect(screen.getAllByText('BUY').length).toBeGreaterThan(0))
    expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(1)
    expect(mockedQuantApi.analyze).toHaveBeenCalledWith('AAPL')
  })

  it('renders HOLD and SELL decisions with the same normal treatment as BUY, never as an error', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'HOLD'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getAllByText('HOLD').length).toBeGreaterThan(0))
    expect(screen.queryByText("Couldn't load this data")).not.toBeInTheDocument()
  })

  it('shows confidence, expected return and expected volatility exactly as returned', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByText('72%')).toBeInTheDocument())
    expect(screen.getByText('+3.40%')).toBeInTheDocument()
    // Expected volatility is genuinely reported twice - once on the decision
    // itself, once inside the risk assessment for the same run - both real.
    expect(screen.getAllByText('18.00%').length).toBeGreaterThan(0)
  })

  it('shows every returned engine, including a failed one, without hiding it or inventing a zero value', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByText('Technical')).toBeInTheDocument())
    expect(screen.getByText('News')).toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
  })

  it('shows the real evidence and risk fields, and separates the explanation from the decision', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByText('Aggregate confidence above threshold')).toBeInTheDocument())
    expect(screen.getByText('MEDIUM')).toBeInTheDocument()
    expect(screen.getByText('0.90')).toBeInTheDocument()
    expect(screen.getByText('Technical momentum outweighs neutral fundamentals.')).toBeInTheDocument()
    expect(screen.getByText(/does not itself determine or adjust that decision/)).toBeInTheDocument()
    expect(screen.queryByText(/stop.loss|take.profit|entry price|ATR|beta|VaR|CVaR/i)).not.toBeInTheDocument()
  })

  it('links the analyzed symbol to its full Asset Explorer page', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByRole('link', { name: /View full asset page/ })).toHaveAttribute('href', '/assets/AAPL'))
  })

  it('analyzing a watchlist symbol reuses the same quant pipeline and never shows a previous symbol\'s stale decision', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY')).mockResolvedValueOnce(pipelineFor('MSFT', 'SELL'))
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'AAPL' }))
    await waitFor(() => expect(screen.getByText('Analysis for AAPL')).toBeInTheDocument())
    await waitFor(() => expect(screen.getAllByText('BUY').length).toBeGreaterThan(0))

    await user.click(screen.getByRole('button', { name: 'MSFT' }))
    await waitFor(() => expect(screen.getByText('Analysis for MSFT')).toBeInTheDocument())
    await waitFor(() => expect(screen.getAllByText('SELL').length).toBeGreaterThan(0))
    expect(screen.queryByText('BUY')).not.toBeInTheDocument()
    expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(2)
  })

  it('shows the real backend error message on a rate-limit failure, never a fabricated result', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockRejectedValueOnce(rateLimitError())
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByText('Rate limit exceeded, try again later.')).toBeInTheDocument())
  })

  it('disables the picker while an analysis is in flight, preventing a duplicate submission', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockImplementation(() => new Promise(() => {}))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByLabelText('Symbol')).toBeDisabled())
    expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(1)
  })

  it('Refresh invalidates system-wide engine status without spending a quant analysis call', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => expect(mockedDashboardApi.engines).toHaveBeenCalledTimes(1))
    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    await waitFor(() => expect(mockedDashboardApi.engines.mock.calls.length).toBeGreaterThan(1))
    expect(mockedQuantApi.analyze).not.toHaveBeenCalled()
  })

  it('renders system engine status independently of the selected symbol', async () => {
    mockedDashboardApi.engines.mockResolvedValueOnce({
      ...engineView,
      engines: [{ engine_name: 'TechnicalEngine', engine_version: '1.0.0', accuracy_by_window: {}, current_weight: 0.5, latest_drift: null }],
    })
    renderPage()
    expect(screen.getByText('System engine status')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('TechnicalEngine')).toBeInTheDocument())
  })
})
