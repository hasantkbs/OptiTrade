import { Button } from './Button'
import styles from './ErrorState.module.css'

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className={styles.wrapper} role="alert">
      <p className={styles.title}>Couldn't load this data</p>
      <p className={styles.message}>{message}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  )
}
