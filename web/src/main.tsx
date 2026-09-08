import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from './theme/ThemeContext'
import { App } from './App'
import './styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Dashboard/analytics data changes on the server's own schedule
      // (see backend/dashboard/scheduler.py) - refetching on every tab
      // focus is unnecessary chatter for this kind of data.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
})

// Matches Vite's own `base` (vite.config.ts) so the router agrees with
// where the app is actually mounted (root locally, /optitrade/ under
// the Algorix integrated deployment) - BASE_URL always has a trailing
// slash, which React Router's basename tolerates fine.
const basename = import.meta.env.BASE_URL.replace(/\/$/, '')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={basename}>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
