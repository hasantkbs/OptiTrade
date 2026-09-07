import { forwardRef, useId, type InputHTMLAttributes } from 'react'
import clsx from 'clsx'
import styles from './Input.module.css'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(({ label, error, id, className, ...rest }, ref) => {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const errorId = error ? `${inputId}-error` : undefined

  return (
    <div className={styles.field}>
      <label htmlFor={inputId} className={styles.label}>
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        className={clsx(styles.input, error && styles.inputError, className)}
        aria-invalid={Boolean(error) || undefined}
        aria-describedby={errorId}
        {...rest}
      />
      {error ? (
        <p id={errorId} className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
})
Input.displayName = 'Input'
