import { NavLink } from 'react-router-dom'
import clsx from 'clsx'
import { NAV_ITEMS } from './nav'
import styles from './Sidebar.module.css'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
  /** Rendered as a slide-over on small screens; the parent controls
   * visibility via this prop rather than the sidebar owning its own
   * breakpoint logic. */
  mobileOpen?: boolean
  onCloseMobile?: () => void
}

export function Sidebar({ collapsed, onToggle, mobileOpen, onCloseMobile }: SidebarProps) {
  return (
    <>
      {mobileOpen ? <div className={styles.scrim} onClick={onCloseMobile} aria-hidden="true" /> : null}
      <aside
        className={clsx(styles.sidebar, collapsed && styles.collapsed, mobileOpen && styles.mobileOpen)}
        aria-label="Primary navigation"
      >
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true">
            OT
          </span>
          {!collapsed && <span className={styles.brandName}>OptiTrade</span>}
        </div>

        <nav className={styles.nav}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              onClick={onCloseMobile}
              className={({ isActive }) => clsx(styles.link, isActive && styles.linkActive)}
              aria-label={item.label}
              title={collapsed ? item.label : undefined}
            >
              <span className={styles.linkLabel} aria-hidden={collapsed || undefined}>
                {!collapsed ? item.label : item.label.slice(0, 2)}
              </span>
              {!item.available && !collapsed ? <span className={styles.soon}>Soon</span> : null}
            </NavLink>
          ))}
        </nav>

        <button
          type="button"
          className={styles.collapseButton}
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <span aria-hidden="true">{collapsed ? '»' : '« Collapse'}</span>
        </button>
      </aside>
    </>
  )
}
