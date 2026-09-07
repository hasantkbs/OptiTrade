import styles from './FullPageSpinner.module.css'

export function FullPageSpinner() {
  return (
    <div className={styles.wrapper} role="status" aria-label="Loading">
      <span className={styles.spinner} aria-hidden="true" />
    </div>
  )
}
