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

interface InviteAuditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  engagementId: string;
}

export function InviteAuditorModal({ isOpen, onClose, engagementId }: InviteAuditorModalProps) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');

  const inviteMutation = useMutation({
    mutationFn: () => auditeaseCompanyApi.inviteAuditor(engagementId, { email }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditease', 'engagements'] });
      toast.success('Auditor invited successfully');
      handleClose();
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to invite auditor');
    }
  });

  const handleClose = () => {
    setEmail('');
    onClose();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !email.includes('@')) {
      toast.error('Valid email is required');
      return;
    }
    inviteMutation.mutate();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-[425px] bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-primary font-heading tracking-wide">
            Invite Auditor
          </DialogTitle>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-medium">
              Auditor Email <span className="text-destructive">*</span>
            </label>
            <Input 
              id="email"
              type="email"
              placeholder="auditor@example.com" 
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="bg-muted/50 focus-visible:ring-primary"
            />
          </div>

          <DialogFooter className="mt-6">
            <Button type="button" variant="ghost" onClick={handleClose}>Cancel</Button>
            <Button 
              type="submit" 
              disabled={inviteMutation.isPending || !email.trim()}
            >
              {inviteMutation.isPending ? 'Inviting...' : 'Send Invite'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
