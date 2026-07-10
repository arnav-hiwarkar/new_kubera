import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { docvaultApi } from '@/api/docvault';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import type { BucketResponse } from '@/types/docvault';
import { Upload } from 'lucide-react';

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  buckets: BucketResponse[];
  currentBucketId: string | null;
}

export function UploadModal({ isOpen, onClose, buckets, currentBucketId }: UploadModalProps) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [bucketId, setBucketId] = useState<string>(currentBucketId || 'none');
  const [tags, setTags] = useState('');
  const [file, setFile] = useState<File | null>(null);

  const uploadMutation = useMutation({
    mutationFn: (formData: FormData) => docvaultApi.uploadDocument(formData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['docvault', 'documents'] });
      toast.success('Document uploaded successfully');
      handleClose();
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to upload document');
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title || !file) return;

    const formData = new FormData();
    formData.append('title', title);
    formData.append('file', file);
    if (bucketId && bucketId !== 'none') {
      formData.append('bucket_id', bucketId);
    }
    if (tags.trim()) {
      formData.append('tags', tags.split(',').map(t => t.trim()).join(','));
    }
    formData.append('is_editable', 'true');

    uploadMutation.mutate(formData);
  };

  const handleClose = () => {
    setTitle('');
    setBucketId(currentBucketId || 'none');
    setTags('');
    setFile(null);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-[425px] bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-primary font-heading tracking-wide">Upload Document</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="title">Title</Label>
            <Input 
              id="title" 
              value={title} 
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. Q3 Financial Report"
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="bucket">Bucket (Optional)</Label>
            <Select value={bucketId} onValueChange={setBucketId}>
              <SelectTrigger id="bucket">
                <SelectValue placeholder="Select a bucket" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Bucket</SelectItem>
                {buckets.map(b => (
                  <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="tags">Tags (comma separated)</Label>
            <Input 
              id="tags" 
              value={tags} 
              onChange={e => setTags(e.target.value)}
              placeholder="e.g. finance, 2026, report"
            />
          </div>

          <div className="space-y-2">
            <Label>File</Label>
            <div className="flex items-center justify-center w-full">
              <label htmlFor="dropzone-file" className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer bg-muted/20 hover:bg-muted/40 transition-colors">
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <Upload className="w-8 h-8 mb-3 text-muted-foreground" />
                  {file ? (
                    <p className="text-sm font-medium text-primary text-center px-4 truncate w-full">
                      {file.name}
                    </p>
                  ) : (
                    <p className="mb-2 text-sm text-muted-foreground text-center px-4">
                      <span className="font-semibold text-foreground">Click to upload</span> or drag and drop
                    </p>
                  )}
                </div>
                <input 
                  id="dropzone-file" 
                  type="file" 
                  className="hidden" 
                  onChange={e => setFile(e.target.files?.[0] || null)}
                  required
                />
              </label>
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button type="button" variant="ghost" onClick={handleClose}>Cancel</Button>
            <Button type="submit" disabled={uploadMutation.isPending || !title || !file}>
              {uploadMutation.isPending ? 'Uploading...' : 'Upload'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
