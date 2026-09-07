import { forwardRef, type ButtonHTMLAttributes } from 'react'
import clsx from 'clsx'
import styles from './Button.module.css'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  isLoading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', isLoading, className, children, disabled, ...rest }, ref) => {
    return (
      <button
        ref={ref}
        className={clsx(styles.button, styles[variant], styles[size], className)}
        disabled={disabled || isLoading}
        aria-busy={isLoading || undefined}
        {...rest}
      >
        {isLoading ? <span className={styles.spinner} aria-hidden="true" /> : null}
        <span className={isLoading ? styles.hiddenLabel : undefined}>{children}</span>
      </button>
    )
  },
)
Button.displayName = 'Button'
