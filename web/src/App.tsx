import { lazy, Suspense, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { AppShell } from './components/layout/AppShell'
import { FullPageSpinner } from './components/ui/FullPageSpinner'
import { LoginPage } from './pages/LoginPage'
import { UnavailablePage } from './pages/UnavailablePage'

// Route-level code splitting: DashboardPage (and its chart sections)
// pulls in recharts, by far the heaviest dependency in this app - no
// reason to make /login pay for it. Every other authenticated page
// splits the same way for consistency.
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const PortfolioPage = lazy(() => import('./pages/PortfolioPage').then((m) => ({ default: m.PortfolioPage })))
const WatchlistPage = lazy(() => import('./pages/WatchlistPage').then((m) => ({ default: m.WatchlistPage })))
const AssetsPage = lazy(() => import('./pages/AssetsPage').then((m) => ({ default: m.AssetsPage })))
const AssetDetailPage = lazy(() => import('./pages/AssetDetailPage').then((m) => ({ default: m.AssetDetailPage })))
const AlertsPage = lazy(() => import('./pages/AlertsPage').then((m) => ({ default: m.AlertsPage })))
const LearningPage = lazy(() => import('./pages/LearningPage').then((m) => ({ default: m.LearningPage })))

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

        <Route
          path="/"
          element={
            <Shell title="Dashboard">
              <DashboardPage />
            </Shell>
          }
        />
        <Route
          path="/portfolio"
          element={
            <Shell title="Portfolio">
              <PortfolioPage />
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
          path="/decisions"
          element={
            <Shell title="Decisions">
              <UnavailablePage
                title="Decisions not available yet"
                description="The backend doesn't currently expose a Decision Engine execution feed over the API."
              />
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
        <Route
          path="/ai-analyst"
          element={
            <Shell title="AI Analyst">
              <UnavailablePage
                title="AI Analyst not available yet"
                description="The backend's explanation engine isn't currently exposed over the API."
              />
            </Shell>
          }
        />
        <Route
          path="/learning"
          element={
            <Shell title="Learning">
              <LearningPage />
            </Shell>
          }
        />
        <Route
          path="/research"
          element={
            <Shell title="Research">
              <UnavailablePage
                title="Research not available yet"
                description="Research Lab is intentionally isolated from the production API and has no public endpoint."
              />
            </Shell>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
