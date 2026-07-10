
import { useParams, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft } from 'lucide-react';
import { AuditorRequirementsTab } from './components/AuditorRequirementsTab';
import { AuditorQueriesTab } from './components/AuditorQueriesTab';
import { AuditorEntriesTab } from './components/AuditorEntriesTab';
import { AuditorTrialBalanceTab } from './components/AuditorTrialBalanceTab';

export default function AuditorEngagementDetailPage() {
  const { id } = useParams<{ id: string }>();

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
           <AuditorTrialBalanceTab engagementId={id!} />
        </TabsContent>
        
        <TabsContent value="requirements" className="flex-1 flex flex-col min-h-0 m-0">
           <AuditorRequirementsTab engagementId={id!} />
        </TabsContent>

        <TabsContent value="queries" className="flex-1 flex flex-col min-h-0 m-0">
           <AuditorQueriesTab engagementId={id!} />
        </TabsContent>

        <TabsContent value="entries" className="flex-1 flex flex-col min-h-0 m-0">
           <AuditorEntriesTab engagementId={id!} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
