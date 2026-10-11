import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'

import { queryClient } from '@/app/query-client'
import { router } from '@/app/router'
import './index.css'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('В index.html нет элемента #root')

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
