import { useAuth } from '../../auth/AuthContext'
import { useTheme } from '../../theme/ThemeContext'
import { useSystemStatus } from '../../features/dashboard/useSystemStatus'
import { useRefreshDashboard } from '../../features/dashboard/hooks'
import { Dropdown } from '../ui/Dropdown'
import { StatusIndicator } from '../ui/StatusIndicator'
import styles from './Header.module.css'

const THEME_LABEL = { light: 'Light', dark: 'Dark', system: 'System' } as const
const STATUS_LABEL = { live: 'System live', degraded: 'Connecting…', offline: 'Backend unreachable' } as const

export function Header({ title, onOpenMobileNav }: { title: string; onOpenMobileNav: () => void }) {
  const { user, logout } = useAuth()
  const { preference, setPreference } = useTheme()
  const status = useSystemStatus()
  const refreshDashboard = useRefreshDashboard()

  return (
    <header className={styles.header}>
      <button
        type="button"
        className={styles.mobileMenuButton}
        onClick={onOpenMobileNav}
        aria-label="Open navigation"
      >
        ☰
      </button>

      <h1 className={styles.title}>{title}</h1>

      <div className={styles.right}>
        <StatusIndicator status={status} label={STATUS_LABEL[status]} />

        <button type="button" className={styles.refreshButton} onClick={refreshDashboard} title="Refresh dashboard data">
          Refresh
        </button>

        <Dropdown
          trigger={<span className={styles.themeTrigger}>Theme: {THEME_LABEL[preference]}</span>}
          items={[
            { label: 'Light', onSelect: () => setPreference('light') },
            { label: 'Dark', onSelect: () => setPreference('dark') },
            { label: 'System', onSelect: () => setPreference('system') },
          ]}
        />

        <Dropdown
          trigger={
            <span className={styles.userTrigger}>
              <span className={styles.avatar} aria-hidden="true">
                {(user?.display_name ?? '?').slice(0, 1).toUpperCase()}
              </span>
              <span className={styles.userName}>{user?.display_name}</span>
            </span>
          }
          items={[{ label: 'Log out', onSelect: () => void logout(), destructive: true }]}
        />
      </div>
    </header>
  )
}
