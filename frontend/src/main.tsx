import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './app'
import './styles.css'

const savedTheme = localStorage.getItem('pv-theme') || 'dark'
const savedDensity = localStorage.getItem('pv-density')
document.documentElement.dataset.theme = savedTheme
if (savedDensity) document.documentElement.dataset.density = savedDensity

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 20_000, retry: 1, refetchOnWindowFocus: true },
    mutations: { retry: 0 },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}><App /></QueryClientProvider>
  </React.StrictMode>,
)
