import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
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
      </div>
    </div>
  )
}
