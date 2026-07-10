import { useQuery } from '@tanstack/react-query';
import { auditeaseAuditorApi } from '@/api/auditease-auditor';
import { useParams, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft } from 'lucide-react';

export default function AuditorEngagementDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data: trialBalance = [], isLoading: tbLoading } = useQuery({
    queryKey: ['auditor', 'engagements', id, 'trial-balance'],
    queryFn: () => auditeaseAuditorApi.getTrialBalance(id!),
    enabled: !!id,
  });

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/auditor/engagements">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <h1 className="text-2xl font-heading tracking-wide text-primary">Engagement Workspace</h1>
      </div>

      <Tabs defaultValue="trial-balance" className="flex-1 flex flex-col min-h-0">
        <TabsList className="w-fit mb-4 bg-muted/50 border border-border">
          <TabsTrigger value="trial-balance">Trial Balance</TabsTrigger>
          <TabsTrigger value="requirements">Requirements</TabsTrigger>
          <TabsTrigger value="queries">Queries</TabsTrigger>
          <TabsTrigger value="entries">Audit Entries</TabsTrigger>
        </TabsList>

        <TabsContent value="trial-balance" className="flex-1 flex flex-col min-h-0 m-0">
          <div className="bg-card border border-border rounded-md p-6">
            <h3 className="text-lg font-medium mb-4">Client Trial Balance</h3>
            {tbLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : trialBalance.length === 0 ? (
              <p className="text-sm text-muted-foreground border border-dashed rounded p-4 text-center">No trial balance accounts available.</p>
            ) : (
              <div className="space-y-2">
                {trialBalance.map(acc => (
                  <div key={acc.id} className="flex justify-between items-center p-3 border border-border rounded-md text-sm">
                    <span>{acc.ledger_code} - {acc.ledger_name}</span>
                    <span className="font-mono">{acc.closing_balance.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </TabsContent>
        
        {/* Placeholder tabs for Requirements, Queries, Entries */}
        <TabsContent value="requirements" className="flex-1 flex flex-col min-h-0 m-0">
           <div className="bg-card border border-border rounded-md p-6">
              <h3 className="text-lg font-medium mb-4">Requirements</h3>
              <p className="text-sm text-muted-foreground">Request documents from the client here.</p>
           </div>
        </TabsContent>

        <TabsContent value="queries" className="flex-1 flex flex-col min-h-0 m-0">
           <div className="bg-card border border-border rounded-md p-6">
              <h3 className="text-lg font-medium mb-4">Queries</h3>
              <p className="text-sm text-muted-foreground">Ask questions and discuss items with the client.</p>
           </div>
        </TabsContent>

        <TabsContent value="entries" className="flex-1 flex flex-col min-h-0 m-0">
           <div className="bg-card border border-border rounded-md p-6">
              <h3 className="text-lg font-medium mb-4">Entries</h3>
              <p className="text-sm text-muted-foreground">Propose audit adjusting entries here.</p>
           </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
