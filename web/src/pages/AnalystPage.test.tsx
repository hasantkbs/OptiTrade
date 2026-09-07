import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AnalystPage } from './AnalystPage'
import { quantApi, watchlistApi } from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  quantApi: { analyze: vi.fn() },
  watchlistApi: { list: vi.fn(), items: vi.fn() },
}))

const mockedQuantApi = vi.mocked(quantApi)
const mockedWatchlistApi = vi.mocked(watchlistApi)

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AnalystPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function pipelineFor(symbol: string, decision: 'BUY' | 'HOLD' | 'SELL') {
  return {
    symbol,
    decision,
    confidence: 0.65,
    expected_return: 0.02,
    expected_volatility: 0.12,
    engine_breakdown: [
      {
        engine_name: 'TechnicalEngine',
        engine_version: '1.0.0',
        status: 'success' as const,
        prediction: decision,
        confidence: 0.7,
        expected_return: 0.03,
        volatility: 0.1,
        evidence: ['Momentum confirms trend'],
      },
      {
        engine_name: 'FundamentalEngine',
        engine_version: '1.0.0',
        status: 'timeout' as const,
        prediction: null,
        confidence: null,
        expected_return: null,
        volatility: null,
        evidence: [],
      },
    ],
    evidence: ['Aggregate confidence above threshold'],
    risk: { risk_level: 'LOW', expected_volatility: 0.12, data_sufficiency: 0.95 },
    explanation: 'Momentum and news sentiment both favor this move.',
    metadata: {
      pipeline_version: '1.0.0',
      total_duration_ms: 90,
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
  error.response = { status: 429, data: { detail: 'Rate limit exceeded.' }, statusText: 'Too Many Requests', headers: {}, config: {} as never }
  return error
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedWatchlistApi.list.mockResolvedValue([{ id: 1, owner: 'user-1', name: 'Core', created_at: '2026-01-01T00:00:00Z' }])
  mockedWatchlistApi.items.mockResolvedValue([
    { id: 1, watchlist_id: 1, symbol: 'AAPL', is_favorite: false, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
    { id: 2, watchlist_id: 1, symbol: 'MSFT', is_favorite: false, folder: null, tags: [], notes: '', added_at: '2026-01-01T00:00:00Z' },
  ])
})

describe('AnalystPage', () => {
  it('renders the header and an honest prompt before any symbol is analyzed', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'AI Analyst' })).toBeInTheDocument()
    expect(screen.getByText(/downstream of the decision/)).toBeInTheDocument()
    expect(screen.getByText(/Pick a symbol above/)).toBeInTheDocument()
  })

  it('analyzes a symbol via the canonical /quant/analyze path and shows decision, confidence and explanation', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))

    await waitFor(() => expect(screen.getAllByText('BUY').length).toBeGreaterThan(0))
    expect(screen.getByText('65%')).toBeInTheDocument()
    expect(screen.getByText('Momentum and news sentiment both favor this move.')).toBeInTheDocument()
    expect(screen.getByText(/does not itself determine or adjust that decision/)).toBeInTheDocument()
    expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(1)
  })

  it('renders HOLD and SELL with the same normal treatment as BUY', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'HOLD'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getAllByText('HOLD').length).toBeGreaterThan(0))
    expect(screen.queryByText("Couldn't load this data")).not.toBeInTheDocument()
  })

  it('shows every engine including a non-success one, and only the three genuine risk fields', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByText('Technical')).toBeInTheDocument())
    expect(screen.getByText('Fundamental')).toBeInTheDocument()
    expect(screen.getByText('timeout')).toBeInTheDocument()
    expect(screen.getByText('LOW')).toBeInTheDocument()
    expect(screen.getByText('0.95')).toBeInTheDocument()
    expect(screen.queryByText(/stop.loss|take.profit|entry price|ATR|beta|VaR|CVaR/i)).not.toBeInTheDocument()
  })

  it('never shows a previous symbol\'s stale decision when switching symbols via the watchlist chips', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValueOnce(pipelineFor('AAPL', 'BUY')).mockResolvedValueOnce(pipelineFor('MSFT', 'SELL'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'AAPL' }))
    await waitFor(() => expect(screen.getAllByText('BUY').length).toBeGreaterThan(0))
    await user.click(screen.getByRole('button', { name: 'MSFT' }))
    await waitFor(() => expect(screen.getAllByText('SELL').length).toBeGreaterThan(0))
    expect(screen.queryByText('BUY')).not.toBeInTheDocument()
  })

  it('re-analyzes only when Refresh analysis is explicitly clicked, never automatically', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockResolvedValue(pipelineFor('AAPL', 'BUY'))
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(1))

    await user.click(screen.getByRole('button', { name: 'Refresh analysis' }))
    await waitFor(() => expect(mockedQuantApi.analyze).toHaveBeenCalledTimes(2))
  })

  it('shows the real error message on a rate-limit failure, never a fabricated result', async () => {
    const user = userEvent.setup()
    mockedQuantApi.analyze.mockRejectedValueOnce(rateLimitError())
    renderPage()
    await user.type(screen.getByLabelText('Symbol'), 'AAPL')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    await waitFor(() => expect(screen.getByText('Rate limit exceeded.')).toBeInTheDocument())
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
})
