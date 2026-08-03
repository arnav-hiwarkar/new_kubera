import { useEffect } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { isRouteErrorResponse, useNavigate, useRouteError } from 'react-router-dom'
import { Button, Card } from '@/components/ui'

export function AppRouteError({ audience }: { audience: 'company' | 'auditor' }) {
  const error = useRouteError()
  const navigate = useNavigate()
  const returnPath = audience === 'auditor' ? '/auditor/app' : '/app/auditease'

  useEffect(() => {
    console.error('Unhandled application route error', error)
  }, [error])

  const description = isRouteErrorResponse(error) && error.status === 404
    ? 'The requested page could not be found.'
    : 'The page encountered an unexpected problem. Reload to get the latest application version.'

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg-base px-4 py-12">
      <Card className="w-full max-w-lg text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-status-action/10 text-status-action">
          <AlertTriangle className="h-6 w-6" />
        </span>
        <h1 className="mt-4 text-xl font-bold text-text-primary">Something went wrong</h1>
        <p className="mt-2 text-sm text-text-secondary">{description}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button onClick={() => window.location.reload()}>
            <RefreshCw /> Reload application
          </Button>
          <Button variant="secondary" onClick={() => navigate(returnPath)}>
            Return to engagements
          </Button>
        </div>
      </Card>
    </main>
  )
}
