import { useState, useRef } from 'react';
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
import { Upload } from 'lucide-react';
import Papa from 'papaparse';
import type { TBImportRow } from '@/types/auditease';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface ImportTBModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ImportTBModal({ isOpen, onClose }: ImportTBModalProps) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [parsedData, setParsedData] = useState<any[]>([]);
  const [step, setStep] = useState<1 | 2>(1);
  
  // Field mapping state (Destination Field -> Source Column Name)
  const [mapping, setMapping] = useState<{
    ledger_code: string;
    ledger_name: string;
    opening_balance: string;
    debit: string;
    credit: string;
    closing_balance: string;
  }>({
    ledger_code: '',
    ledger_name: '',
    opening_balance: '',
    debit: '',
    credit: '',
    closing_balance: '',
  });

  const importMutation = useMutation({
    mutationFn: (rows: TBImportRow[]) => auditeaseCompanyApi.importTrialBalance(rows),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['auditease', 'trial-balance'] });
      toast.success(`Imported ${data.length} accounts successfully`);
      handleClose();
    },
    onError: (error: any) => {
      toast.error(error.message || 'Failed to import Trial Balance');
    }
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;
    setFile(selectedFile);

    Papa.parse(selectedFile, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.meta.fields) {
          setHeaders(results.meta.fields);
          setParsedData(results.data);
          
          // Auto-guess mapping based on common names
          const guessMapping: any = { ...mapping };
          const f = results.meta.fields.map(h => h.toLowerCase());
          
          results.meta.fields.forEach(header => {
            const lower = header.toLowerCase();
            if (lower.includes('code') || lower.includes('id')) guessMapping.ledger_code = header;
            if (lower.includes('name') || lower.includes('desc') || lower.includes('ledger')) guessMapping.ledger_name = header;
            if (lower.includes('open')) guessMapping.opening_balance = header;
            if (lower.includes('debit') || lower.includes('dr')) guessMapping.debit = header;
            if (lower.includes('credit') || lower.includes('cr')) guessMapping.credit = header;
            if (lower.includes('close') || lower.includes('bal')) guessMapping.closing_balance = header;
          });
          
          setMapping(guessMapping);
          setStep(2);
        }
      },
      error: (error) => {
        toast.error('Failed to parse CSV: ' + error.message);
      }
    });
  };

  const handleImport = () => {
    if (!mapping.ledger_name) {
      toast.error('Ledger Name mapping is required');
      return;
    }

    const parseNumber = (val: any) => {
      if (!val) return 0;
      const num = parseFloat(val.toString().replace(/,/g, ''));
      return isNaN(num) ? 0 : num;
    };

    const rows: TBImportRow[] = parsedData.map(row => ({
      ledger_code: mapping.ledger_code ? row[mapping.ledger_code] : null,
      ledger_name: row[mapping.ledger_name] || 'Unknown',
      opening_balance: mapping.opening_balance ? parseNumber(row[mapping.opening_balance]) : 0,
      debit: mapping.debit ? parseNumber(row[mapping.debit]) : 0,
      credit: mapping.credit ? parseNumber(row[mapping.credit]) : 0,
      closing_balance: mapping.closing_balance ? parseNumber(row[mapping.closing_balance]) : 0,
    }));

    importMutation.mutate(rows);
  };

  const handleClose = () => {
    setFile(null);
    setHeaders([]);
    setParsedData([]);
    setStep(1);
    onClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-[500px] bg-card border-border">
        <DialogHeader>
          <DialogTitle className="text-primary font-heading tracking-wide">
            {step === 1 ? 'Import Trial Balance' : 'Map Columns'}
          </DialogTitle>
        </DialogHeader>
        
        {step === 1 && (
          <div className="space-y-4 py-4">
            <div className="flex items-center justify-center w-full">
              <label htmlFor="csv-file" className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer bg-muted/20 hover:bg-muted/40 transition-colors">
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <Upload className="w-8 h-8 mb-3 text-muted-foreground" />
                  <p className="mb-2 text-sm text-muted-foreground text-center px-4">
                    <span className="font-semibold text-foreground">Click to upload CSV</span>
                  </p>
                </div>
                <input 
                  id="csv-file" 
                  type="file" 
                  accept=".csv"
                  className="hidden" 
                  onChange={handleFileChange}
                />
              </label>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4 py-4">
            <p className="text-sm text-muted-foreground mb-4">
              Map your CSV columns to the Trial Balance fields.
            </p>
            
            <div className="grid grid-cols-2 gap-4">
              {Object.keys(mapping).map((fieldKey) => (
                <div key={fieldKey} className="space-y-2">
                  <label className="text-xs font-medium capitalize">
                    {fieldKey.replace('_', ' ')}
                    {fieldKey === 'ledger_name' && <span className="text-destructive ml-1">*</span>}
                  </label>
                  <Select 
                    value={(mapping as any)[fieldKey]} 
                    onValueChange={(val) => setMapping(prev => ({ ...prev, [fieldKey]: val }))}
                  >
                    <SelectTrigger className="h-8">
                      <SelectValue placeholder="Select column..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">-- Ignore --</SelectItem>
                      {headers.map(h => (
                        <SelectItem key={h} value={h}>{h}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>

            <DialogFooter className="mt-6">
              <Button type="button" variant="ghost" onClick={() => setStep(1)}>Back</Button>
              <Button 
                type="button" 
                onClick={handleImport}
                disabled={importMutation.isPending || !mapping.ledger_name}
              >
                {importMutation.isPending ? 'Importing...' : 'Import Data'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
