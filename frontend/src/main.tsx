import React from 'react'
import ReactDOM from 'react-dom/client'
<<<<<<< HEAD
import App from './App'
=======
import { RouterProvider } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { router } from '@/routes'
import { queryClient } from '@/lib/queryClient'
import { ToastProvider } from '@/components/ui/Toast'
>>>>>>> new_frontend
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
<<<<<<< HEAD
    <App />
  </React.StrictMode>
=======
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </React.StrictMode>,
>>>>>>> new_frontend
)
