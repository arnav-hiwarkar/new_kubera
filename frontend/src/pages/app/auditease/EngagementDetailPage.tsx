import { useQuery } from '@tanstack/react-query';
import { auditeaseCompanyApi } from '@/api/auditease-company';
import { useParams, Link } from 'react-router-dom';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ArrowLeft, MessageSquare, FileText, CheckCircle2, UserPlus } from 'lucide-react';
import { format } from 'date-fns';
import { InviteAuditorModal } from '@/components/auditease/InviteAuditorModal';

export default function EngagementDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);

  // Fetch all related data
  const { data: requirements = [], isLoading: reqLoading } = useQuery({
    queryKey: ['auditease', 'engagements', id, 'requirements'],
    queryFn: () => auditeaseCompanyApi.getRequirements(id!),
    enabled: !!id,
  });

  const { data: queries = [], isLoading: queriesLoading } = useQuery({
    queryKey: ['auditease', 'engagements', id, 'queries'],
    queryFn: () => auditeaseCompanyApi.getQueries(id!),
    enabled: !!id,
  });

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/app/auditease">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <h1 className="text-2xl font-heading tracking-wide text-primary">Engagement Details</h1>
        </div>
        <Button onClick={() => setIsInviteModalOpen(true)} className="bg-secondary text-secondary-foreground hover:bg-secondary/90">
          <UserPlus className="mr-2 h-4 w-4" />
          Invite Auditor
        </Button>
      </div>

      <Tabs defaultValue="requirements" className="flex-1 flex flex-col min-h-0">
        <TabsList className="w-fit mb-4 bg-muted/50 border border-border">
          <TabsTrigger value="requirements">Requirements</TabsTrigger>
          <TabsTrigger value="queries">Queries</TabsTrigger>
          <TabsTrigger value="entries">Audit Entries</TabsTrigger>
        </TabsList>

        <TabsContent value="requirements" className="flex-1 flex flex-col min-h-0 m-0">
          <div className="bg-card border border-border rounded-md p-6 space-y-4">
            <h3 className="text-lg font-medium flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Document Requirements
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              Documents requested by your auditor.
            </p>
            
            {reqLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : requirements.length === 0 ? (
              <p className="text-sm text-muted-foreground border border-dashed rounded p-4 text-center">No requirements found.</p>
            ) : (
              <div className="space-y-3">
                {requirements.map(req => (
                  <div key={req.id} className="flex items-center justify-between p-4 border border-border rounded-md bg-muted/20">
                    <div>
                      <p className="font-medium">{req.description}</p>
                      <p className="text-xs text-muted-foreground mt-1">Requested {format(new Date(req.created_at), 'MMM d, yyyy')}</p>
                    </div>
                    <div>
                      {req.status === 'open' ? (
                        <Button size="sm">Fulfill</Button>
                      ) : (
                        <span className="flex items-center text-sm text-green-500 font-medium">
                          <CheckCircle2 className="h-4 w-4 mr-1" /> Fulfilled
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        <TabsContent value="queries" className="flex-1 flex flex-col min-h-0 m-0">
          <div className="bg-card border border-border rounded-md p-6 space-y-4">
            <h3 className="text-lg font-medium flex items-center gap-2">
              <MessageSquare className="h-5 w-5 text-primary" />
              Audit Queries
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              Questions and clarifications requested by the auditor.
            </p>

            {queriesLoading ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : queries.length === 0 ? (
              <p className="text-sm text-muted-foreground border border-dashed rounded p-4 text-center">No queries open.</p>
            ) : (
              <div className="space-y-4">
                {queries.map(q => (
                  <div key={q.id} className="border border-border rounded-md p-4">
                    <div className="flex justify-between items-center mb-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${q.status === 'open' ? 'bg-yellow-500/10 text-yellow-500' : 'bg-green-500/10 text-green-500'}`}>
                        {q.status.toUpperCase()}
                      </span>
                      <span className="text-xs text-muted-foreground">{format(new Date(q.created_at), 'MMM d')}</span>
                    </div>
                    <div className="space-y-2 mt-4">
                      {q.messages.map(msg => (
                        <div key={msg.id} className={`p-3 rounded-md text-sm ${msg.sender_type === 'company_user' ? 'bg-primary/10 ml-8' : 'bg-muted mr-8'}`}>
                          <p className="font-semibold text-xs mb-1 opacity-70">
                            {msg.sender_type === 'company_user' ? 'You' : 'Auditor'}
                          </p>
                          <p>{msg.text}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </TabsContent>
        
        <TabsContent value="entries" className="flex-1 flex flex-col min-h-0 m-0">
           <div className="bg-card border border-border rounded-md p-6">
              <h3 className="text-lg font-medium flex items-center gap-2 mb-4">
                Proposed Entries
              </h3>
              <p className="text-sm text-muted-foreground">Entries proposed by the auditor will appear here for your approval.</p>
           </div>
        </TabsContent>
      </Tabs>

      <InviteAuditorModal 
        isOpen={isInviteModalOpen}
        onClose={() => setIsInviteModalOpen(false)}
        engagementId={id!}
      />
    </div>
  );
}
