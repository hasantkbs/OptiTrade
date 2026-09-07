/**
 * Central nav definition - `available: true` only for routes backed by
 * a real endpoint the dashboard already integrates (see src/api/endpoints.ts
 * and each page's own data hooks). `available: false` routes still
 * render (WEB STEP 1 §3: "do not fabricate functionality") but show an
 * explicit "not available yet" page instead of a working feature.
 */
export interface NavItem {
  to: string
  label: string
  available: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', available: true },
  { to: '/portfolio', label: 'Portfolio', available: true },
  { to: '/watchlist', label: 'Watchlist', available: true },
  { to: '/assets', label: 'Assets', available: true },
  { to: '/decisions', label: 'Decisions', available: false },
  { to: '/alerts', label: 'Alerts', available: true },
  { to: '/ai-analyst', label: 'AI Analyst', available: false },
  { to: '/learning', label: 'Learning', available: true },
  { to: '/research', label: 'Research', available: false },
]
