import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { auditeaseAuditorApi } from '@/api/auditease-auditor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { FileText, Pencil, Trash2, Plus } from 'lucide-react';

export function AuditorRequirementsTab({ engagementId }: { engagementId: string }) {
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');

  const { data: requirements = [], isLoading } = useQuery({
    queryKey: ['auditor', 'engagements', engagementId, 'requirements'],
    queryFn: () => auditeaseAuditorApi.getRequirements(engagementId),
    enabled: !!engagementId,
  });

  const createMutation = useMutation({
    mutationFn: (data: { title: string; description: string }) => auditeaseAuditorApi.createRequirement(engagementId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'requirements'] });
      setIsCreating(false);
      setTitle('');
      setDescription('');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: { reqId: string; payload: { title: string; description: string } }) => auditeaseAuditorApi.updateRequirement(engagementId, data.reqId, data.payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'requirements'] });
      setEditingId(null);
      setTitle('');
      setDescription('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (reqId: string) => auditeaseAuditorApi.deleteRequirement(engagementId, reqId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'requirements'] });
    },
  });

  const handleSave = () => {
    if (!title.trim() || !description.trim()) return;
    if (editingId) {
      updateMutation.mutate({ reqId: editingId, payload: { title, description } });
    } else {
      createMutation.mutate({ title, description });
    }
  };

  const handleEdit = (req: any) => {
    setIsCreating(true);
    setEditingId(req.id);
    setTitle(req.title);
    setDescription(req.description);
  };

  const handleCancel = () => {
    setIsCreating(false);
    setEditingId(null);
    setTitle('');
    setDescription('');
  };

  if (isLoading) return <div className="text-sm text-muted-foreground p-6">Loading requirements...</div>;

  return (
    <div className="bg-card border border-border rounded-md p-6 h-full flex flex-col">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h3 className="text-lg font-medium text-foreground">Requirement Requests</h3>
          <p className="text-sm text-muted-foreground">Request documents and information from the client.</p>
        </div>
        {!isCreating && (
          <Button onClick={() => setIsCreating(true)} size="sm">
            <Plus className="h-4 w-4 mr-2" />
            New Request
          </Button>
        )}
      </div>

      {isCreating && (
        <div className="mb-6 p-4 border border-border rounded-md bg-muted/30 space-y-4">
          <div>
            <label className="text-sm font-medium mb-1 block">Title</label>
            <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Bank Statements Q3" />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Description</label>
            <Textarea value={description} onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)} placeholder="Provide details about what is required..." className="min-h-[100px]" />
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="outline" size="sm" onClick={handleCancel}>Cancel</Button>
            <Button size="sm" onClick={handleSave} disabled={createMutation.isPending || updateMutation.isPending}>
              {editingId ? 'Save Changes' : 'Create Request'}
            </Button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-4">
        {requirements.length === 0 && !isCreating ? (
          <div className="text-center p-8 border border-dashed border-border rounded-md">
            <FileText className="h-8 w-8 mx-auto text-muted-foreground mb-3 opacity-50" />
            <p className="text-sm text-muted-foreground">No requirement requests yet.</p>
          </div>
        ) : (
          requirements.map((req) => (
            <div key={req.id} className="p-4 border border-border rounded-md bg-muted/10 flex flex-col gap-3">
              <div className="flex justify-between items-start">
                <div>
                  <h4 className="font-medium text-foreground">{req.title}</h4>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${req.status === 'fulfilled' ? 'bg-green-500/10 text-green-500' : 'bg-yellow-500/10 text-yellow-500'}`}>
                      {req.status.toUpperCase()}
                    </span>
                    <span className="text-xs text-muted-foreground">{new Date(req.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                {req.status === 'open' && (
                  <div className="flex gap-2">
                    <Button variant="ghost" size="icon" onClick={() => handleEdit(req)} className="h-8 w-8">
                      <Pencil className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => deleteMutation.mutate(req.id)} className="h-8 w-8">
                      <Trash2 className="h-4 w-4 text-destructive opacity-70 hover:opacity-100" />
                    </Button>
                  </div>
                )}
              </div>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{req.description}</p>
              
              {req.status === 'fulfilled' && req.fulfilled_document_id && (
                <div className="mt-2 pt-3 border-t border-border flex items-center gap-2">
                  <FileText className="h-4 w-4 text-primary" />
                  <span className="text-sm text-foreground">Document Fulfilled (ID: {req.fulfilled_document_id})</span>
                  {/* Ideally, add a link to view/download via docVault API */}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
