import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { docvaultApi } from '@/api/docvault';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { Download, Upload, Clock } from 'lucide-react';
import type { DocumentResponse, BucketResponse, DocumentStatus } from '@/types/docvault';
import { cn } from '@/lib/utils';

interface DocumentDetailModalProps {
  document: DocumentResponse;
  isOpen: boolean;
  onClose: () => void;
  buckets: BucketResponse[];
}

export function DocumentDetailModal({ document, isOpen, onClose, buckets }: DocumentDetailModalProps) {
  const queryClient = useQueryClient();
  const [isUploadingVersion, setIsUploadingVersion] = useState(false);
  const [versionFile, setVersionFile] = useState<File | null>(null);

  const updateMutation = useMutation({
    mutationFn: (status: DocumentStatus) => docvaultApi.updateDocument(document.id, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['docvault', 'documents'] });
      toast.success('Document status updated');
    },
    onError: () => toast.error('Failed to update status')
  });

  const uploadVersionMutation = useMutation({
    mutationFn: (formData: FormData) => docvaultApi.uploadVersion(document.id, formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['docvault', 'documents'] });
      toast.success('New version uploaded');
      setIsUploadingVersion(false);
      setVersionFile(null);
    },
    onError: () => toast.error('Failed to upload version')
  });

  const handleDownload = async () => {
    try {
      const blob = await docvaultApi.downloadDocument(document.id);
      const url = window.URL.createObjectURL(blob);
      const a = window.document.createElement('a');
      a.href = url;
      a.download = document.title;
      window.document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      window.document.body.removeChild(a);
    } catch (error) {
      toast.error('Download failed');
    }
  };

  const handleUploadVersion = () => {
    if (!versionFile) return;
    const formData = new FormData();
    formData.append('file', versionFile);
    uploadVersionMutation.mutate(formData);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'uploaded': return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'pending_approval': return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';
      case 'action_required': return 'bg-destructive/10 text-destructive border-destructive/20';
      case 'verified': return 'bg-green-500/10 text-green-500 border-green-500/20';
      case 'submitted': return 'bg-purple-500/10 text-purple-500 border-purple-500/20';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[600px] bg-card border-border max-h-[85vh] flex flex-col p-0">
        <DialogHeader className="px-6 py-4 border-b border-border">
          <DialogTitle className="text-xl font-heading tracking-wide text-primary">
            {document.title}
          </DialogTitle>
        </DialogHeader>
        
        <ScrollArea className="flex-1 px-6 py-4">
          <div className="space-y-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm text-muted-foreground mb-1">Status</p>
                <div className="flex items-center gap-3">
                  <Badge variant="outline" className={cn("capitalize font-normal text-sm px-3", getStatusColor(document.status))}>
                    {document.status.replace('_', ' ')}
                  </Badge>
                  <Select 
                    value={document.status} 
                    onValueChange={(val) => updateMutation.mutate(val as DocumentStatus)}
                  >
                    <SelectTrigger className="w-[180px] h-8 text-xs">
                      <SelectValue placeholder="Update status..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="uploaded">Uploaded</SelectItem>
                      <SelectItem value="pending_approval">Pending Approval</SelectItem>
                      <SelectItem value="action_required">Action Required</SelectItem>
                      <SelectItem value="verified">Verified</SelectItem>
                      <SelectItem value="submitted">Submitted</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              
              <Button onClick={handleDownload} variant="outline" size="sm" className="h-8">
                <Download className="mr-2 h-4 w-4" /> Download Latest
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground mb-1">Bucket</p>
                <p className="font-medium text-foreground">
                  {buckets.find(b => b.id === document.bucket_id)?.name || 'None'}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground mb-1">Last Updated</p>
                <p className="font-medium text-foreground">
                  {format(new Date(document.updated_at), 'MMM d, yyyy h:mm a')}
                </p>
              </div>
              <div className="col-span-2">
                <p className="text-muted-foreground mb-1">Tags</p>
                <div className="flex flex-wrap gap-2">
                  {document.tags.length > 0 ? document.tags.map(tag => (
                    <span key={tag} className="px-2.5 py-1 bg-muted rounded-full text-xs font-medium text-muted-foreground">
                      {tag}
                    </span>
                  )) : (
                    <span className="text-muted-foreground italic text-xs">No tags</span>
                  )}
                </div>
              </div>
            </div>

            <div className="pt-4 border-t border-border">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-heading tracking-wide text-foreground flex items-center gap-2">
                  <Clock className="h-4 w-4 text-primary" /> Version History
                </h3>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={() => setIsUploadingVersion(!isUploadingVersion)}
                  className="text-xs h-8"
                >
                  <Upload className="mr-2 h-3 w-3" /> New Version
                </Button>
              </div>

              {isUploadingVersion && (
                <div className="mb-4 p-4 border border-border rounded-md bg-muted/20 flex items-center gap-3">
                  <Input 
                    type="file" 
                    className="text-xs"
                    onChange={e => setVersionFile(e.target.files?.[0] || null)}
                  />
                  <Button 
                    size="sm" 
                    onClick={handleUploadVersion}
                    disabled={!versionFile || uploadVersionMutation.isPending}
                  >
                    {uploadVersionMutation.isPending ? 'Uploading...' : 'Upload'}
                  </Button>
                </div>
              )}

              <div className="space-y-3">
                {document.versions.sort((a, b) => b.version_number - a.version_number).map((v, i) => (
                  <div key={v.id} className="flex items-center justify-between p-3 rounded-md border border-border bg-card">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium flex items-center gap-2">
                        v{v.version_number}
                        {i === 0 && <Badge variant="secondary" className="text-[10px] h-4 px-1.5 bg-primary/20 text-primary">Latest</Badge>}
                      </span>
                      <span className="text-xs text-muted-foreground mt-0.5">
                        {v.original_filename} • {(v.size_bytes / 1024).toFixed(1)} KB
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {format(new Date(v.uploaded_at), 'MMM d, yyyy')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
