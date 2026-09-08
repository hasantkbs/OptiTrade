import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { authApi } from '../api/endpoints'
import { apiErrorMessage } from '../api/client'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import styles from './RegisterPage.module.css'

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

interface FieldErrors {
  email?: string
  password?: string
  confirmPassword?: string
}

export function RegisterPage() {
  const { status } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  function validate(): FieldErrors {
    const errors: FieldErrors = {}
    if (!email.trim()) {
      errors.email = 'Email is required.'
    } else if (!EMAIL_PATTERN.test(email.trim())) {
      errors.email = 'Enter a valid email address.'
    }
    if (!password) {
      errors.password = 'Password is required.'
    }
    if (password && confirmPassword !== password) {
      errors.confirmPassword = 'Passwords do not match.'
    }
    return errors
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errors = validate()
    setFieldErrors(errors)
    setSubmitError(null)
    if (Object.keys(errors).length > 0) return

    setSubmitting(true)
    try {
      // The backend account-creation contract (users/schemas.py's
      // RegisterRequest) requires a display_name and returns only the
      // created user, not a session (POST /auth/register -> UserResponse,
      // no tokens) - registration therefore never touches auth state
      // here, it only creates the account. The signup form intentionally
      // only asks for email/password, so the local part of the email is
      // used as a reasonable default the user can change later from
      // their profile.
      await authApi.register({
        email: email.trim(),
        password,
        display_name: email.trim().split('@')[0],
      })
      void navigate('/login', { state: { justRegistered: true }, replace: true })
    } catch (error) {
      setSubmitError(apiErrorMessage(error, 'Could not create your account. Please try again.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            OT
          </span>
          <span className={styles.brandName}>OptiTrade</span>
        </div>
        <p className={styles.tagline}>Create your account</p>

        <form className={styles.form} onSubmit={handleSubmit} noValidate>
          <Input
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            error={fieldErrors.email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Input
            label="Password"
            type="password"
            name="password"
            autoComplete="new-password"
            required
            value={password}
            error={fieldErrors.password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <Input
            label="Confirm password"
            type="password"
            name="confirmPassword"
            autoComplete="new-password"
            required
            value={confirmPassword}
            error={fieldErrors.confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />

          {submitError ? (
            <p className={styles.error} role="alert">
              {submitError}
            </p>
          ) : null}

          <Button type="submit" isLoading={submitting} className={styles.submit}>
            Create account
          </Button>
        </form>

        <p className={styles.footer}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
