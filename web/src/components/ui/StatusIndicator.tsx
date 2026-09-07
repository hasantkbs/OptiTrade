import clsx from 'clsx'
import styles from './StatusIndicator.module.css'

type Status = 'live' | 'degraded' | 'offline'

const LABEL: Record<Status, string> = {
  live: 'Live',
  degraded: 'Degraded',
  offline: 'Offline',
}

/**
 * The shell's signature detail: a small, quiet pulse next to the
 * system-status readout, signalling "this is a live monitoring
 * surface" rather than a static report. Respects reduced-motion
 * (see global.css) and never appears anywhere data isn't actually
 * live-checked.
 */
export function StatusIndicator({ status, label }: { status: Status; label?: string }) {
  return (
    <span className={styles.wrapper} role="status">
      <span className={clsx(styles.dot, styles[status])} aria-hidden="true" />
      <span className={styles.label}>{label ?? LABEL[status]}</span>
    </span>
  )
}
