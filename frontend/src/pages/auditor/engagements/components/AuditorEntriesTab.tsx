import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { auditeaseAuditorApi } from '@/api/auditease-auditor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, Trash2, Edit3, X, AlertCircle } from 'lucide-react';
import type { AuditEntryResponse, EntryLineSide, AuditEntryLineBase } from '@/types/auditease';

export function AuditorEntriesTab({ engagementId }: { engagementId: string }) {
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [lines, setLines] = useState<AuditEntryLineBase[]>([]);

  const { data: entries = [], isLoading: entriesLoading } = useQuery({
    queryKey: ['auditor', 'engagements', engagementId, 'entries'],
    queryFn: () => auditeaseAuditorApi.getEntries(engagementId),
    enabled: !!engagementId,
  });

  const { data: trialBalance = [] } = useQuery({
    queryKey: ['auditor', 'engagements', engagementId, 'trial-balance'],
    queryFn: () => auditeaseAuditorApi.getTrialBalance(engagementId),
    enabled: !!engagementId,
  });

  const createMutation = useMutation({
    mutationFn: (payload: any) => auditeaseAuditorApi.createEntry(engagementId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'entries'] });
      resetForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: (payload: { id: string; data: any }) => auditeaseAuditorApi.updateEntry(engagementId, payload.id, payload.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auditor', 'engagements', engagementId, 'entries'] });
      resetForm();
    },
  });

  const resetForm = () => {
    setIsCreating(false);
    setEditingId(null);
    setCode('');
    setDescription('');
    setLines([]);
  };

  const handleCreateNew = () => {
    setIsCreating(true);
    setEditingId(null);
    // Auto-generate code AJE-1, AJE-2 etc based on existing
    const prefix = 'AJE-';
    let nextNum = 1;
    if (entries.length > 0) {
      const nums = entries.map((e: AuditEntryResponse) => {
        if (e.code && e.code.startsWith(prefix)) {
          return parseInt(e.code.substring(prefix.length)) || 0;
        }
        return 0;
      });
      nextNum = Math.max(...nums) + 1;
    }
    setCode(`${prefix}${nextNum}`);
    setDescription('');
    setLines([
      { ledger_id: '', side: 'debit', amount: 0 },
      { ledger_id: '', side: 'credit', amount: 0 }
    ]);
  };

  const handleEdit = (entry: AuditEntryResponse) => {
    setIsCreating(true);
    setEditingId(entry.id);
    setCode(entry.code || '');
    setDescription(entry.description);
    setLines(entry.lines.map(l => ({ ledger_id: l.ledger_id, side: l.side, amount: l.amount })));
  };

  const addLine = () => {
    setLines([...lines, { ledger_id: '', side: 'debit', amount: 0 }]);
  };

  const updateLine = (index: number, field: keyof AuditEntryLineBase, value: any) => {
    const newLines = [...lines];
    newLines[index] = { ...newLines[index], [field]: value };
    setLines(newLines);
  };

  const removeLine = (index: number) => {
    setLines(lines.filter((_, i) => i !== index));
  };

  const totals = useMemo(() => {
    let debit = 0;
    let credit = 0;
    lines.forEach(l => {
      if (l.side === 'debit') debit += Number(l.amount) || 0;
      if (l.side === 'credit') credit += Number(l.amount) || 0;
    });
    return { debit, credit, isBalanced: debit === credit && debit > 0 };
  }, [lines]);

  const hasDuplicateLedgers = useMemo(() => {
    const ids = lines.map(l => l.ledger_id).filter(id => id !== '');
    return new Set(ids).size !== ids.length;
  }, [lines]);

  const isValid = code.trim() && description.trim() && lines.every(l => l.ledger_id && l.amount > 0) && totals.isBalanced && !hasDuplicateLedgers;

  const handleSubmit = () => {
    if (!isValid) return;
    const payload = { code, description, lines };
    if (editingId) {
      updateMutation.mutate({ id: editingId, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  };

  if (entriesLoading) return <div className="text-sm text-muted-foreground p-6">Loading entries...</div>;

  if (isCreating || editingId) {
    return (
      <div className="bg-card border border-border rounded-md p-6 flex flex-col gap-6">
        <div className="flex justify-between items-center">
          <h3 className="text-lg font-medium">{editingId ? 'Edit Entry' : 'New Audit Entry'}</h3>
          <Button variant="ghost" size="icon" onClick={resetForm}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="grid grid-cols-4 gap-4">
          <div className="col-span-1">
            <label className="text-sm font-medium mb-1 block">Entry Code</label>
            <Input value={code} onChange={e => setCode(e.target.value)} placeholder="AJE-1" />
          </div>
          <div className="col-span-3">
            <label className="text-sm font-medium mb-1 block">Description</label>
            <Input value={description} onChange={e => setDescription(e.target.value)} placeholder="To adjust..." />
          </div>
        </div>

        <div>
          <div className="flex justify-between items-end mb-2">
            <label className="text-sm font-medium">Lines</label>
            <Button variant="outline" size="sm" onClick={addLine}>
              <Plus className="h-4 w-4 mr-2" />
              Add Line
            </Button>
          </div>
          
          <div className="space-y-2 mb-4">
            {lines.map((line, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <Select value={line.ledger_id} onValueChange={v => updateLine(idx, 'ledger_id', v)}>
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select Ledger Account" />
                  </SelectTrigger>
                  <SelectContent>
                    {trialBalance.map((acc: any) => (
                      <SelectItem key={acc.id} value={acc.id}>
                        {acc.ledger_code ? `${acc.ledger_code} - ` : ''}{acc.ledger_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={line.side} onValueChange={(v: EntryLineSide) => updateLine(idx, 'side', v)}>
                  <SelectTrigger className="w-[120px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="debit">Debit</SelectItem>
                    <SelectItem value="credit">Credit</SelectItem>
                  </SelectContent>
                </Select>
                <Input 
                  type="number" 
                  min="0" 
                  step="0.01" 
                  value={line.amount || ''} 
                  onChange={e => updateLine(idx, 'amount', parseFloat(e.target.value))} 
                  className="w-[150px] font-mono text-right"
                  placeholder="0.00"
                />
                <Button variant="ghost" size="icon" onClick={() => removeLine(idx)} disabled={lines.length <= 2}>
                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                </Button>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between p-4 bg-muted/20 border border-border rounded-md">
            <div className="flex flex-col gap-1">
              {!totals.isBalanced && (
                <span className="text-xs text-destructive flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" /> Debits and credits must balance.
                </span>
              )}
              {hasDuplicateLedgers && (
                <span className="text-xs text-destructive flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" /> Each ledger can only be selected once.
                </span>
              )}
            </div>
            <div className="flex gap-6 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Total Debit:</span>
                <span className="font-mono font-medium">{totals.debit.toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Total Credit:</span>
                <span className="font-mono font-medium">{totals.credit.toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={resetForm}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!isValid || createMutation.isPending || updateMutation.isPending}>
            {editingId ? 'Resubmit Entry' : 'Propose Entry'}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-md p-6 h-full flex flex-col">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h3 className="text-lg font-medium text-foreground">Audit Entries</h3>
          <p className="text-sm text-muted-foreground">Propose adjusting journal entries to the client.</p>
        </div>
        <Button onClick={handleCreateNew} size="sm">
          <Plus className="h-4 w-4 mr-2" />
          New Entry
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4">
        {entries.length === 0 ? (
          <div className="text-center p-8 border border-dashed border-border rounded-md">
            <Edit3 className="h-8 w-8 mx-auto text-muted-foreground mb-3 opacity-50" />
            <p className="text-sm text-muted-foreground">No audit entries proposed yet.</p>
          </div>
        ) : (
          entries.map((entry: AuditEntryResponse) => {
            const isRejected = entry.status === 'rejected';
            return (
              <div key={entry.id} className="p-4 border border-border rounded-md bg-muted/10">
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h4 className="font-medium text-foreground">{entry.code}</h4>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        entry.status === 'approved' ? 'bg-green-500/10 text-green-500' :
                        entry.status === 'rejected' ? 'bg-red-500/10 text-red-500' :
                        'bg-blue-500/10 text-blue-500'
                      }`}>
                        {entry.status.toUpperCase()}
                      </span>
                    </div>
                    <p className="text-sm text-muted-foreground">{entry.description}</p>
                  </div>
                  {isRejected && (
                    <Button variant="outline" size="sm" onClick={() => handleEdit(entry)}>
                      <Edit3 className="h-4 w-4 mr-2" />
                      Edit & Resubmit
                    </Button>
                  )}
                </div>
                
                {isRejected && entry.rejection_comment && (
                  <div className="mb-4 p-3 bg-red-500/5 border border-red-500/20 rounded-md">
                    <p className="text-sm font-medium text-red-500 mb-1">Rejection Reason:</p>
                    <p className="text-sm text-muted-foreground">{entry.rejection_comment}</p>
                  </div>
                )}

                <div className="bg-background rounded border border-border overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 border-b border-border">
                      <tr>
                        <th className="text-left font-medium p-2 text-muted-foreground">Ledger</th>
                        <th className="text-right font-medium p-2 text-muted-foreground w-32">Debit</th>
                        <th className="text-right font-medium p-2 text-muted-foreground w-32">Credit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {entry.lines.map((line: any) => {
                        const ledger = trialBalance.find((t: any) => t.id === line.ledger_id);
                        return (
                          <tr key={line.id} className="border-b border-border last:border-0">
                            <td className="p-2 truncate">{ledger ? `${ledger.ledger_code || ''} ${ledger.ledger_name}` : 'Unknown Ledger'}</td>
                            <td className="p-2 text-right font-mono">{line.side === 'debit' ? line.amount.toLocaleString() : ''}</td>
                            <td className="p-2 text-right font-mono">{line.side === 'credit' ? line.amount.toLocaleString() : ''}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
