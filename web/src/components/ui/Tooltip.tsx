import { useId, useState, type ReactNode } from 'react'
import styles from './Tooltip.module.css'

export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  const [visible, setVisible] = useState(false)
  const id = useId()

  return (
    <span
      className={styles.wrapper}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      <span aria-describedby={visible ? id : undefined}>{children}</span>
      {visible ? (
        <span role="tooltip" id={id} className={styles.bubble}>
          {content}
        </span>
      ) : null}
    </span>
  )
}
