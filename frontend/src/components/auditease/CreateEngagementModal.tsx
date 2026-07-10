import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { auditeaseCompanyApi } from '@/api/auditease-company';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { toast } from 'sonner';

interface CreateEngagementModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreateEngagementModal({ isOpen, onClose }: CreateEngagementModalProps) {
  const queryClient = useQueryClient();
  const [periodLabel, setPeriodLabel] = useState('');

  const createMutation = useMutation({
    mutationFn: () => auditeaseCompanyApi.createEngagement({ period_label: periodLabel }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditease', 'engagements'] });
      toast.success('Engagement created successfully');
      handleClose();
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to create engagement');
    }
  });

  const handleClose = () => {
    setPeriodLabel('');
    onClose();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!periodLabel.trim()) {
      toast.error('Period label is required');
      return;
    }
    createMutation.mutate();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-[425px] bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-primary font-heading tracking-wide">
            New Audit Engagement
          </DialogTitle>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="period" className="text-sm font-medium">
              Financial Period <span className="text-destructive">*</span>
            </label>
            <Input 
              id="period"
              placeholder="e.g. FY 2023-24" 
              value={periodLabel}
              onChange={(e) => setPeriodLabel(e.target.value)}
              className="bg-muted/50 focus-visible:ring-primary"
            />
          </div>

          <DialogFooter className="mt-6">
            <Button type="button" variant="ghost" onClick={handleClose}>Cancel</Button>
            <Button 
              type="submit" 
              disabled={createMutation.isPending || !periodLabel.trim()}
            >
              {createMutation.isPending ? 'Creating...' : 'Create Engagement'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
