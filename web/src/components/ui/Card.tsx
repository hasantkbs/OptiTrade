import type { HTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'
import styles from './Card.module.css'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  padding?: 'none' | 'compact' | 'default'
}

export function Card({ children, padding = 'default', className, ...rest }: CardProps) {
  return (
    <div className={clsx(styles.card, styles[`padding-${padding}`], className)} {...rest}>
      {children}
    </div>
  )
}

export function CardHeader({ children, className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={clsx(styles.header, className)} {...rest}>
      {children}
    </div>
  )
}

export function CardTitle({ children, className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={clsx(styles.title, className)} {...rest}>
      {children}
    </h3>
  )
}

export function CardSubtitle({ children, className, ...rest }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={clsx(styles.subtitle, className)} {...rest}>
      {children}
    </p>
  )
}
