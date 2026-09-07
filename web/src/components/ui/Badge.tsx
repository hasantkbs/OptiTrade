import type { HTMLAttributes } from 'react'
import clsx from 'clsx'
import styles from './Badge.module.css'

type BadgeTone = 'neutral' | 'positive' | 'negative' | 'warning' | 'info' | 'accent'

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone
}

export function Badge({ tone = 'neutral', className, children, ...rest }: BadgeProps) {
  return (
    <span className={clsx(styles.badge, styles[tone], className)} {...rest}>
      {children}
    </span>
  )
}
