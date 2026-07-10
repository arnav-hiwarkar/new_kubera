import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { auditeaseCompanyApi } from '@/api/auditease-company';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ImportTBModal } from '@/components/auditease/ImportTBModal';
import { TrialBalanceTable } from '@/components/auditease/TrialBalanceTable';
import { CreateEngagementModal } from '@/components/auditease/CreateEngagementModal';
import { Upload, Plus, Trash2 } from 'lucide-react';
import { format } from 'date-fns';
import { useNavigate } from 'react-router-dom';
import { useAppAuth } from '@/contexts/AppAuthContext';
import { toast } from 'sonner';

export default function AuditEasePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { role } = useAppAuth();
  const isAdmin = role === 'admin';
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isCreateEngagementOpen, setIsCreateEngagementOpen] = useState(false);

  const { data: tbAccounts = [], isLoading: tbLoading } = useQuery({
    queryKey: ['auditease', 'trial-balance'],
    queryFn: auditeaseCompanyApi.getTrialBalance,
  });

  const { data: engagements = [], isLoading: engagementsLoading } = useQuery({
    queryKey: ['auditease', 'engagements'],
    queryFn: auditeaseCompanyApi.getEngagements,
  });

  const deleteEngagementMutation = useMutation({
    mutationFn: auditeaseCompanyApi.deleteEngagement,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditease', 'engagements'] });
      toast.success('Engagement deleted successfully');
    },
    onError: (err: any) => {
      toast.error(err.response?.data?.detail || 'Failed to delete engagement');
    }
  });

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this engagement? This action cannot be undone.')) {
      deleteEngagementMutation.mutate(id);
    }
  };

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-heading tracking-wide text-primary">AuditEase</h1>
      </div>

      <Tabs defaultValue="trial-balance" className="flex-1 flex flex-col min-h-0">
        <TabsList className="w-fit mb-4 bg-muted/50 border border-border">
          <TabsTrigger value="trial-balance">Trial Balance</TabsTrigger>
          <TabsTrigger value="engagements">Engagements</TabsTrigger>
        </TabsList>

        <TabsContent value="trial-balance" className="flex-1 flex flex-col min-h-0 m-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium">Trial Balance</h2>
            <Button 
              onClick={() => setIsImportModalOpen(true)}
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <Upload className="mr-2 h-4 w-4" />
              Import CSV
            </Button>
          </div>

          <div className="flex-1 overflow-hidden flex flex-col">
            <TrialBalanceTable tbAccounts={tbAccounts} isLoading={tbLoading} isReadOnly={false} />
          </div>
        </TabsContent>

        <TabsContent value="engagements" className="flex-1 flex flex-col min-h-0 m-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-medium">Audit Engagements</h2>
            <Button 
              className="bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={() => setIsCreateEngagementOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              New Engagement
            </Button>
          </div>

          <div className="rounded-md border border-border bg-card flex-1 overflow-hidden flex flex-col">
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="hover:bg-transparent">
                  <TableHead>Period</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  {isAdmin && <TableHead className="text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {engagementsLoading ? (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center py-8 text-muted-foreground">
                      Loading engagements...
                    </TableCell>
                  </TableRow>
                ) : engagements.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center py-8 text-muted-foreground">
                      No active audit engagements.
                    </TableCell>
                  </TableRow>
                ) : (
                  engagements.map((eng) => (
                    <TableRow 
                      key={eng.id} 
                      className="cursor-pointer hover:bg-muted/30 transition-colors"
                      onClick={() => navigate(`/app/auditease/engagements/${eng.id}`)}
                    >
                      <TableCell className="font-medium">{eng.period_label}</TableCell>
                      <TableCell>
                        <span className="px-2.5 py-1 bg-muted rounded-full text-xs text-muted-foreground capitalize">
                          {eng.status}
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {format(new Date(eng.created_at), 'MMM d, yyyy')}
                      </TableCell>
                      {isAdmin && (
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive h-8 w-8"
                            onClick={(e) => handleDelete(e, eng.id)}
                            disabled={deleteEngagementMutation.isPending}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </TabsContent>
      </Tabs>

      <ImportTBModal 
        isOpen={isImportModalOpen} 
        onClose={() => setIsImportModalOpen(false)} 
      />

      <CreateEngagementModal 
        isOpen={isCreateEngagementOpen}
        onClose={() => setIsCreateEngagementOpen(false)}
      />
    </div>
  );
}
