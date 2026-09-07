import clsx from 'clsx'
import styles from './Skeleton.module.css'

export function Skeleton({ width, height = '1rem', className }: { width?: string; height?: string; className?: string }) {
  return (
    <span
      className={clsx(styles.skeleton, className)}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}

export function SkeletonCard() {
  return (
    <div className={styles.card}>
      <Skeleton width="40%" height="0.75rem" />
      <Skeleton width="65%" height="1.5rem" />
      <Skeleton width="90%" height="0.75rem" />
    </div>
  )
}
