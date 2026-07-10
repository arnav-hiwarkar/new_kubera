
import { useQuery } from '@tanstack/react-query';
import { auditeaseAuditorApi } from '@/api/auditease-auditor';
import { TrialBalanceTable } from '@/components/auditease/TrialBalanceTable';

export function AuditorTrialBalanceTab({ engagementId }: { engagementId: string }) {
  const { data: trialBalance = [], isLoading: tbLoading } = useQuery({
    queryKey: ['auditor', 'engagements', engagementId, 'trial-balance'],
    queryFn: () => auditeaseAuditorApi.getTrialBalance(engagementId),
    enabled: !!engagementId,
  });

  return (
    <div className="flex-1 flex flex-col h-full">
      <TrialBalanceTable tbAccounts={trialBalance} isLoading={tbLoading} isReadOnly={true} />
    </div>
  );
}
