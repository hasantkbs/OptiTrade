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
  { to: '/', label: 'Market', available: true },
  { to: '/watchlist', label: 'Watchlist', available: true },
  { to: '/assets', label: 'Assets', available: true },
  { to: '/alerts', label: 'Alerts', available: true },
]
