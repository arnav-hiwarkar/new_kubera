import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { docvaultApi } from '@/api/docvault';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Folder, FileText, Search, Plus, MoreHorizontal } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import type { BucketResponse, DocumentResponse } from '@/types/docvault';
import { UploadModal } from '@/components/docvault/UploadModal';
import { DocumentDetailModal } from '@/components/docvault/DocumentDetailModal';

export default function DocVaultPage() {
  const queryClient = useQueryClient();
  const [selectedBucketId, setSelectedBucketId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<DocumentResponse | null>(null);

  const { data: buckets = [], isLoading: bucketsLoading } = useQuery({
    queryKey: ['docvault', 'buckets'],
    queryFn: docvaultApi.getBuckets,
  });

  const { data: documents = [], isLoading: docsLoading } = useQuery({
    queryKey: ['docvault', 'documents', selectedBucketId],
    queryFn: () => docvaultApi.getDocuments(selectedBucketId || undefined),
  });

  const filteredDocs = documents.filter(doc => 
    doc.title.toLowerCase().includes(searchQuery.toLowerCase()) || 
    doc.tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const createBucketMutation = useMutation({
    mutationFn: (name: string) => docvaultApi.createBucket({ name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['docvault', 'buckets'] });
    }
  });

  const handleCreateBucket = () => {
    const name = window.prompt('Enter new bucket name:');
    if (name) {
      createBucketMutation.mutate(name);
    }
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
    <div className="flex h-full flex-col md:flex-row gap-6">
      {/* Buckets Sidebar */}
      <div className="w-full md:w-64 flex-shrink-0 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-heading tracking-wide text-primary">Buckets</h2>
          <Button variant="ghost" size="icon" onClick={handleCreateBucket}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        
        <div className="space-y-1">
          <button
            onClick={() => setSelectedBucketId(null)}
            className={cn(
              "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              selectedBucketId === null
                ? "bg-primary/10 text-primary font-medium"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            )}
          >
            <Folder className="h-4 w-4" />
            All Documents
          </button>
          
          {buckets.map(bucket => (
            <button
              key={bucket.id}
              onClick={() => setSelectedBucketId(bucket.id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                selectedBucketId === bucket.id
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
              )}
            >
              <Folder className="h-4 w-4" />
              {bucket.name}
            </button>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-6">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search documents or tags..."
              className="pl-9 bg-card border-muted-foreground/20"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Button 
            onClick={() => setIsUploadModalOpen(true)}
            className="bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="mr-2 h-4 w-4" />
            Upload Document
          </Button>
        </div>

        <div className="rounded-md border border-border bg-card flex-1 overflow-hidden flex flex-col">
          <Table>
            <TableHeader className="bg-muted/50">
              <TableRow className="hover:bg-transparent">
                <TableHead>Document</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Bucket</TableHead>
                <TableHead>Tags</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {docsLoading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                    Loading documents...
                  </TableCell>
                </TableRow>
              ) : filteredDocs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                    No documents found.
                  </TableCell>
                </TableRow>
              ) : (
                filteredDocs.map((doc) => (
                  <TableRow 
                    key={doc.id}
                    className="cursor-pointer hover:bg-muted/30 transition-colors"
                    onClick={() => setSelectedDocument(doc)}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <FileText className="h-4 w-4 text-primary" />
                        <span className="font-medium">{doc.title}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn("capitalize font-normal", getStatusColor(doc.status))}>
                        {doc.status.replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {buckets.find(b => b.id === doc.bucket_id)?.name || '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {doc.tags.map(tag => (
                          <span key={tag} className="px-2 py-0.5 bg-muted rounded-full text-xs text-muted-foreground">
                            {tag}
                          </span>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {format(new Date(doc.updated_at), 'MMM d, yyyy')}
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <UploadModal 
        isOpen={isUploadModalOpen} 
        onClose={() => setIsUploadModalOpen(false)}
        buckets={buckets}
        currentBucketId={selectedBucketId}
      />

      {selectedDocument && (
        <DocumentDetailModal
          document={selectedDocument}
          isOpen={!!selectedDocument}
          onClose={() => setSelectedDocument(null)}
          buckets={buckets}
        />
      )}
    </div>
  );
}
