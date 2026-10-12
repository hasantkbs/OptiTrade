import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MarketOpportunities } from './MarketOpportunities'
import { marketApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({
  marketApi: { opportunities: vi.fn() },
}))

const mockedMarketApi = vi.mocked(marketApi)

function renderComponent() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MarketOpportunities />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('MarketOpportunities', () => {
  it('defaults to the US tab and shows its ranked opportunities', async () => {
    mockedMarketApi.opportunities.mockResolvedValueOnce({
      market: 'US',
      opportunities: [
        {
          rank: 1, symbol: 'AAPL', decision: 'BUY', label: 'STRONG_BUY_BIAS', confidence: 0.82,
          expected_return: 0.045, expected_volatility: 0.18, risk_bucket: 'LOW',
        },
      ],
      total_scanned_count: 28, failed_count: 0, generated_at: '2026-01-01T00:00:00Z',
    })
    renderComponent()

    expect(await screen.findByRole('link', { name: 'AAPL' })).toHaveAttribute('href', '/assets/AAPL')
    expect(screen.getByText('Strong Buy')).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('4.50%')).toBeInTheDocument()
  })

  it('shows an honest "still analyzing" state on a 503 (cold cache), not a generic error', async () => {
    mockedMarketApi.opportunities.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 503, data: { detail: 'not ready' } },
    })
    renderComponent()

    expect(await screen.findByText('Still analyzing this market')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('shows a retryable error state for a real failure', async () => {
    mockedMarketApi.opportunities.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 500, data: { detail: 'boom' } },
    })
    renderComponent()

    expect(await screen.findByText('boom')).toBeInTheDocument()
  })

  it('switches markets on tab click and fetches that market', async () => {
    const user = userEvent.setup()
    mockedMarketApi.opportunities.mockImplementation((market: string) =>
      Promise.resolve({
        market, opportunities: [], total_scanned_count: 0, failed_count: 0,
        generated_at: '2026-01-01T00:00:00Z',
      }),
    )
    renderComponent()

    await waitFor(() => expect(mockedMarketApi.opportunities).toHaveBeenCalledWith('US'))

    await user.click(screen.getByRole('tab', { name: 'BIST (TR)' }))
    await waitFor(() => expect(mockedMarketApi.opportunities).toHaveBeenCalledWith('TR'))
  })
})
