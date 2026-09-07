import type { ReactNode } from 'react'
import { ResponsiveContainer } from 'recharts'
import { SkeletonCard } from './Skeleton'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import styles from './ChartContainer.module.css'

interface ChartContainerProps {
  /** Screen-reader label describing what the chart shows - charts
   * themselves are not meaningfully readable by assistive tech. */
  label: string
  height?: number
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
  isEmpty?: boolean
  emptyTitle?: string
  emptyDescription?: string
  emptyVariant?: 'empty' | 'unavailable'
  children: ReactNode
}

/**
 * Every chart on the dashboard renders through this so loading/empty/
 * error states are handled once, consistently, rather than per-chart.
 * `children` is the actual recharts <LineChart>/<AreaChart>/etc. -
 * ResponsiveContainer is applied here so callers never fix a pixel
 * width.
 */
export function ChartContainer({
  label,
  height = 260,
  isLoading,
  error,
  onRetry,
  isEmpty,
  emptyTitle = 'No data yet',
  emptyDescription,
  emptyVariant = 'empty',
  children,
}: ChartContainerProps) {
  if (isLoading) {
    return (
      <div style={{ height }}>
        <SkeletonCard />
      </div>
    )
  }

  if (error) {
    return <ErrorState message={error} onRetry={onRetry} />
  }

  if (isEmpty) {
    return <EmptyState title={emptyTitle} description={emptyDescription} variant={emptyVariant} />
  }

  return (
    <div className={styles.wrapper} style={{ height }} role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  )
}
