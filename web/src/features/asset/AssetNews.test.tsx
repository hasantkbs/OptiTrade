import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AssetNews } from './AssetNews'
import type { NewsSummaryResponse } from '../../api/types'

const news: NewsSummaryResponse = {
  symbol: 'AAPL', sector: 'Technology', market: 'US', total_news: 2, analyzed_news: 2,
  sentiment_score: 0.4, sentiment_label: 'Positive', score_delta: 0.1, positive_count: 2,
  negative_count: 0, neutral_count: 0, signals: [], top_positive_title: 'Great quarter', top_negative_title: null,
  fetched_at: '2026-01-01T00:00:00Z',
  headlines: [
    { title: 'Great quarter', sentiment: 'POSITIVE', score: 0.6, age_weight: 1, keywords: [], published_at: '2026-01-01T00:00:00Z' },
    { title: 'New product launch', sentiment: 'POSITIVE', score: 0.3, age_weight: 0.8, keywords: [], published_at: '2025-12-30T00:00:00Z' },
  ],
  error: null,
}

describe('AssetNews', () => {
  it('shows a loading state', () => {
    render(<AssetNews isLoading isError={false} onRetry={vi.fn()} />)
    expect(screen.getByText('News')).toBeInTheDocument()
  })

  it('shows a clean "no news" state for an empty headlines list', () => {
    render(<AssetNews news={{ ...news, headlines: [] }} isLoading={false} isError={false} onRetry={vi.fn()} />)
    expect(screen.getByText('No recent news for this symbol.')).toBeInTheDocument()
  })

  it('renders real headlines with sentiment, never fabricated ones', () => {
    render(<AssetNews news={news} isLoading={false} isError={false} onRetry={vi.fn()} />)
    expect(screen.getByText('Great quarter')).toBeInTheDocument()
    expect(screen.getByText('New product launch')).toBeInTheDocument()
    expect(screen.getAllByText('Positive')).toHaveLength(2)
  })

  it('shows a retryable error state and calls onRetry when clicked', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(<AssetNews isLoading={false} isError errorMessage="network error" onRetry={onRetry} />)
    expect(screen.getByText('network error')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /try again/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
