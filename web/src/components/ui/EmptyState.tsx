import type { ReactNode } from 'react'
import styles from './EmptyState.module.css'

/**
 * For a section with no data yet (a real, empty query result) or a
 * backend capability that doesn't exist yet - `variant="unavailable"`
 * makes that distinction explicit instead of presenting both the same
 * way. Never used to disguise a fabricated placeholder as real data.
 */
export function EmptyState({
  title,
  description,
  action,
  variant = 'empty',
}: {
  title: string
  description?: string
  action?: ReactNode
  variant?: 'empty' | 'unavailable'
}) {
  return (
    <div className={styles.wrapper} data-variant={variant}>
      <p className={styles.title}>{title}</p>
      {description ? <p className={styles.description}>{description}</p> : null}
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  )
}
