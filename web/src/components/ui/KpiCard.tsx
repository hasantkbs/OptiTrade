import type { ReactNode } from 'react'
import clsx from 'clsx'
import { Card } from './Card'
import { Skeleton } from './Skeleton'
import { Tooltip } from './Tooltip'
import styles from './KpiCard.module.css'

interface KpiCardProps {
  label: string
  value?: ReactNode
  isLoading?: boolean
  tone?: 'neutral' | 'positive' | 'negative'
  hint?: string
  /** Explains a less-obvious metric (WEB STEP 2 §3) - rendered as a small info affordance next to the label. */
  tooltip?: string
  /** The backend genuinely has nothing for this metric (no portfolio, no data yet) - shown as an
   * explicit "—" rather than a 0 or a fabricated placeholder (WEB STEP 2 §3, §16). */
  isUnavailable?: boolean
  unavailableReason?: string
}

export function KpiCard({
  label,
  value,
  isLoading,
  tone = 'neutral',
  hint,
  tooltip,
  isUnavailable,
  unavailableReason,
}: KpiCardProps) {
  const labelNode = tooltip ? (
    <Tooltip content={tooltip}>
      <span className={styles.labelWithHint}>
        {label}
        <span className={styles.hintMark} aria-hidden="true">
          ?
        </span>
      </span>
    </Tooltip>
  ) : (
    label
  )

  return (
    <Card padding="compact" className={styles.card}>
      <span className={styles.label}>{labelNode}</span>
      {isLoading ? (
        <Skeleton width="60%" height="1.75rem" />
      ) : isUnavailable ? (
        <span className={clsx(styles.value, styles.unavailable)} title={unavailableReason}>
          —
        </span>
      ) : (
        <span className={clsx('num', styles.value, styles[tone])}>{value}</span>
      )}
      {isUnavailable && unavailableReason ? (
        <span className={styles.hint}>{unavailableReason}</span>
      ) : hint ? (
        <span className={styles.hint}>{hint}</span>
      ) : null}
    </Card>
  )
}
