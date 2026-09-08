import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import styles from './LoginPage.module.css'

export function LoginPage() {
  const { status, login, loginError } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // Set only by a redirect from RegisterPage right after a successful
  // POST /auth/register - that endpoint returns the created account, not
  // a session (see RegisterPage's own comment), so this is the point
  // where the user is told to actually sign in.
  const justRegistered = Boolean((location.state as { justRegistered?: boolean } | null)?.justRegistered)

  if (status === 'authenticated') {
    const from = (location.state as { from?: Location } | null)?.from
    return <Navigate to={from?.pathname ?? '/'} replace />
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    try {
      await login(email, password)
    } catch {
      // loginError is already set by AuthContext; nothing further to do here.
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
        <p className={styles.tagline}>Quant analytics &amp; decision intelligence</p>

        {justRegistered ? (
          <p className={styles.success} role="status">
            Account created. Sign in to continue.
          </p>
        ) : null}

        <form className={styles.form} onSubmit={handleSubmit}>
          <Input
            label="Email"
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Input
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {loginError ? (
            <p className={styles.error} role="alert">
              {loginError}
            </p>
          ) : null}

          <Button type="submit" isLoading={submitting} className={styles.submit}>
            Sign in
          </Button>
        </form>

        <p className={styles.footer}>
          Don&apos;t have an account? <Link to="/register">Create account</Link>
        </p>
      </div>
    </div>
  )
}
