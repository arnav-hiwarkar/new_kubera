import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { auditeaseAuditorApi } from '@/api/auditease-auditor';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { format } from 'date-fns';
import { CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

export default function EngagementsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: engagements = [], isLoading } = useQuery({
    queryKey: ['auditor', 'engagements'],
    queryFn: auditeaseAuditorApi.getEngagements,
  });

  const acceptMutation = useMutation({
    mutationFn: (id: string) => auditeaseAuditorApi.acceptEngagement(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements'] });
      toast.success('Engagement accepted');
    },
    onError: () => {
      toast.error('Failed to accept engagement');
    }
  });

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-heading tracking-wide text-primary">My Engagements</h1>
      </div>

      <div className="rounded-md border border-border bg-card flex-1 overflow-hidden flex flex-col">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow className="hover:bg-transparent">
              <TableHead>Company</TableHead>
              <TableHead>Period</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Invited On</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                  Loading engagements...
                </TableCell>
              </TableRow>
            ) : engagements.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                  You have no audit engagements yet.
                </TableCell>
              </TableRow>
            ) : (
              engagements.map((eng) => (
                <TableRow key={eng.id} className="hover:bg-muted/30 transition-colors">
                  <TableCell className="font-medium">Company {eng.company_id.slice(0, 8)}</TableCell>
                  <TableCell>{eng.period_label}</TableCell>
                  <TableCell>
                    <span className="px-2.5 py-1 bg-muted rounded-full text-xs text-muted-foreground capitalize">
                      {eng.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {format(new Date(eng.created_at), 'MMM d, yyyy')}
                  </TableCell>
                  <TableCell className="text-right">
                    {eng.status === 'invited' ? (
                      <Button 
                        size="sm" 
                        className="h-8"
                        onClick={() => acceptMutation.mutate(eng.id)}
                        disabled={acceptMutation.isPending}
                      >
                        <CheckCircle2 className="mr-2 h-4 w-4" /> Accept
                      </Button>
                    ) : (
                      <Button 
                        variant="outline" 
                        size="sm" 
                        className="h-8"
                        onClick={() => navigate(`/auditor/engagements/${eng.id}`)}
                      >
                        View Details
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
