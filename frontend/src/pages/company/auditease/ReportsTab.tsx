import { Card, Button, Spinner, useToast, EmptyState } from '@/components/ui'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { companyClient } from '@/api/clients/company'

function useGenerateReport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (engagementId: string) =>
      companyClient.post<{ id: string; url: string }>(`/api/v1/auditease/engagements/${engagementId}/reports/generate`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['docvault', 'documents'] })
    },
  })
}

export function ReportsTab({ engagementId }: { engagementId: string }) {
  const generate = useGenerateReport()
  const toast = useToast()

  const handleGenerate = async () => {
    try {
      await generate.mutateAsync(engagementId)
      toast.success('Report generated and saved to docVault')
    } catch (e: any) {
      toast.error(e.message || 'Failed to generate report')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-text-primary">Reports</h3>
          <p className="text-sm text-text-muted">Generate Annual Reports (PnL + Balance Sheet) from your approved trial balance.</p>
        </div>
        <Button onClick={handleGenerate} loading={generate.isPending}>
          Generate New Report
        </Button>
      </div>
      
      <Card>
        <p className="text-sm text-text-secondary">
          Generated reports are automatically saved to your <strong>docVault</strong> under the "Final Reports" bucket.
        </p>
      </Card>
    </div>
  )
}
