import { useEffect, type ReactNode } from 'react'
import styles from './Dialog.module.css'

interface DialogProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

/**
 * A small generic modal primitive for a form, not a yes/no decision -
 * `role="dialog"` (not ConfirmDialog's `role="alertdialog"`), and a
 * `children` slot instead of a fixed description/confirm-button shape.
 * Same overlay/card visual language as ConfirmDialog (the app's only
 * other modal) so a new dialog never introduces a second look.
 */
export function Dialog({ open, title, onClose, children }: DialogProps) {
  useEffect(() => {
    if (!open) return
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="dialog-title" className={styles.title}>
          {title}
        </h2>
        {children}
      </div>
    </div>
  )
}
