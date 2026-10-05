import { Badge } from '../../components/ui/Badge'
import { Card, CardHeader, CardTitle } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { SkeletonCard } from '../../components/ui/Skeleton'
import type { NewsSummaryResponse } from '../../api/types'
import styles from './AssetNews.module.css'

function sentimentTone(label: string): 'positive' | 'negative' | 'neutral' {
  const lower = label.toLowerCase()
  if (lower.includes('pos') || lower.includes('bull')) return 'positive'
  if (lower.includes('neg') || lower.includes('bear')) return 'negative'
  return 'neutral'
}

const SENTIMENT_LABELS: Record<string, string> = {
  POSITIVE: 'Positive',
  SLIGHTLY_POSITIVE: 'Slightly positive',
  NEUTRAL: 'Neutral',
  SLIGHTLY_NEGATIVE: 'Slightly negative',
  NEGATIVE: 'Negative',
}

function sentimentLabel(label: string): string {
  return SENTIMENT_LABELS[label] ?? label
}

interface AssetNewsProps {
  news?: NewsSummaryResponse
  isLoading: boolean
  isError: boolean
  errorMessage?: string
  onRetry: () => void
}

/**
 * Backed entirely by GET /news/{symbol} (core/news_analyzer.py::
 * get_news_summary) - a real, already-existing endpoint never called
 * from the frontend until now. Shows up to 5 real headlines with
 * their real sentiment label; raw score/age_weight/keywords fields
 * are not displayed.
 */
export function AssetNews({ news, isLoading, isError, errorMessage, onRetry }: AssetNewsProps) {
  const headlines = news?.headlines.slice(0, 5) ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>News</CardTitle>
      </CardHeader>

      {isLoading ? <SkeletonCard /> : null}
      {isError ? <ErrorState message={errorMessage ?? "Couldn't load news"} onRetry={onRetry} /> : null}

      {!isLoading && !isError && headlines.length === 0 ? (
        <p className={styles.empty}>No recent news for this symbol.</p>
      ) : null}

      {!isLoading && !isError && headlines.length > 0 ? (
        <ul className={styles.list}>
          {headlines.map((item, index) => (
            <li key={index} className={styles.row}>
              <span className={styles.title}>{item.title}</span>
              <Badge tone={sentimentTone(item.sentiment)}>{sentimentLabel(item.sentiment)}</Badge>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  )
}
