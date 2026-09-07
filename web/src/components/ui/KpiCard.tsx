import type { ReactNode } from 'react'
import clsx from 'clsx'
import { Card } from './Card'
import { Skeleton } from './Skeleton'
import styles from './KpiCard.module.css'

interface KpiCardProps {
  label: string
  value?: ReactNode
  isLoading?: boolean
  tone?: 'neutral' | 'positive' | 'negative'
  hint?: string
}

export function KpiCard({ label, value, isLoading, tone = 'neutral', hint }: KpiCardProps) {
  return (
    <Card padding="compact" className={styles.card}>
      <span className={styles.label}>{label}</span>
      {isLoading ? (
        <Skeleton width="60%" height="1.75rem" />
      ) : (
        <span className={clsx('num', styles.value, styles[tone])}>{value}</span>
      )}
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </Card>
  )
}
