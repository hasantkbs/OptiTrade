import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { AppShell } from './components/layout/AppShell'
import { FullPageSpinner } from './components/ui/FullPageSpinner'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'

// Route-level code splitting: MarketSnapshotPage pulls in recharts, by
// far the heaviest dependency in this app - no reason to make /login
// pay for it. Every other authenticated page splits the same way.
const MarketSnapshotPage = lazy(() => import('./pages/MarketSnapshotPage').then((m) => ({ default: m.MarketSnapshotPage })))
const WatchlistPage = lazy(() => import('./pages/WatchlistPage').then((m) => ({ default: m.WatchlistPage })))
const AssetsPage = lazy(() => import('./pages/AssetsPage').then((m) => ({ default: m.AssetsPage })))
const AssetDetailPage = lazy(() => import('./pages/AssetDetailPage').then((m) => ({ default: m.AssetDetailPage })))
const AlertsPage = lazy(() => import('./pages/AlertsPage').then((m) => ({ default: m.AlertsPage })))

function Shell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <ProtectedRoute>
      <AppShell title={title}>
        <Suspense fallback={<FullPageSpinner />}>{children}</Suspense>
      </AppShell>
    </ProtectedRoute>
  )
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route
          path="/"
          element={
            <Shell title="Market">
              <MarketSnapshotPage />
            </Shell>
          }
        />
        <Route
          path="/watchlist"
          element={
            <Shell title="Watchlist">
              <WatchlistPage />
            </Shell>
          }
        />
        <Route
          path="/assets"
          element={
            <Shell title="Assets">
              <AssetsPage />
            </Shell>
          }
        />
        <Route
          path="/assets/:symbol"
          element={
            <Shell title="Asset">
              <AssetDetailPage />
            </Shell>
          }
        />
        <Route
          path="/alerts"
          element={
            <Shell title="Alerts">
              <AlertsPage />
            </Shell>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
