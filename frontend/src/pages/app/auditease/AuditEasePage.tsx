import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
import { CreateEngagementModal } from '@/components/auditease/CreateEngagementModal';
import { Upload, Plus } from 'lucide-react';
import { format } from 'date-fns';
import { useNavigate } from 'react-router-dom';

export default function AuditEasePage() {
  const navigate = useNavigate();
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

          <div className="rounded-md border border-border bg-card flex-1 overflow-hidden flex flex-col">
            <Table>
              <TableHeader className="bg-muted/50">
                <TableRow className="hover:bg-transparent">
                  <TableHead>Code</TableHead>
                  <TableHead>Ledger Name</TableHead>
                  <TableHead className="text-right">Opening</TableHead>
                  <TableHead className="text-right">Debit</TableHead>
                  <TableHead className="text-right">Credit</TableHead>
                  <TableHead className="text-right">Closing</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tbLoading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      Loading trial balance...
                    </TableCell>
                  </TableRow>
                ) : tbAccounts.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      No accounts found. Import a Trial Balance CSV to get started.
                    </TableCell>
                  </TableRow>
                ) : (
                  tbAccounts.map((acc) => (
                    <TableRow key={acc.id} className="hover:bg-muted/30 transition-colors">
                      <TableCell className="font-mono text-xs text-muted-foreground">{acc.ledger_code || '—'}</TableCell>
                      <TableCell className="font-medium">{acc.ledger_name}</TableCell>
                      <TableCell className="text-right">{acc.opening_balance.toLocaleString()}</TableCell>
                      <TableCell className="text-right text-destructive">{acc.debit.toLocaleString()}</TableCell>
                      <TableCell className="text-right text-green-500">{acc.credit.toLocaleString()}</TableCell>
                      <TableCell className="text-right font-medium">{acc.closing_balance.toLocaleString()}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
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
