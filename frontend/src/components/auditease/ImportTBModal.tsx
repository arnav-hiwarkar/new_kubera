import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { auditeaseCompanyApi } from '@/api/auditease-company';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { toast } from 'sonner';
import { Upload, FileSpreadsheet } from 'lucide-react';
import Papa from 'papaparse';
import * as XLSX from 'xlsx';
import type { TBImportRow } from '@/types/auditease';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface ImportTBModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ImportTBModal({ isOpen, onClose }: ImportTBModalProps) {
  const queryClient = useQueryClient();
  const [fileType, setFileType] = useState<'csv' | 'xlsx' | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [parsedData, setParsedData] = useState<any[]>([]);
  const [step, setStep] = useState<1 | 2 | 3>(1); // 1=Upload, 2=Select Sheet, 3=Map Columns
  
  // XLSX specific state
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null);
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string>('');
  
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

  const autoGuessMapping = (fields: string[]) => {
    const guessMapping: any = { 
      ledger_code: '',
      ledger_name: '',
      opening_balance: '',
      debit: '',
      credit: '',
      closing_balance: '',
    };
    
    fields.forEach(header => {
      if (!header) return;
      const lower = header.toLowerCase();
      if (lower.includes('code') || lower.includes('id')) guessMapping.ledger_code = header;
      if (lower.includes('name') || lower.includes('desc') || lower.includes('ledger')) guessMapping.ledger_name = header;
      if (lower.includes('open')) guessMapping.opening_balance = header;
      if (lower.includes('debit') || lower.includes('dr')) guessMapping.debit = header;
      if (lower.includes('credit') || lower.includes('cr')) guessMapping.credit = header;
      if (lower.includes('close') || lower.includes('bal')) guessMapping.closing_balance = header;
    });
    
    setMapping(guessMapping);
  };

  const processSheetData = (ws: XLSX.WorkSheet) => {
    // header: 1 returns an array of arrays
    const rawData = XLSX.utils.sheet_to_json<any[]>(ws, { header: 1 });
    if (rawData.length === 0) {
      toast.error('The selected sheet is empty.');
      return;
    }
    
    // Find the first row that actually looks like a header row
    let headerRowIndex = 0;
    for (let i = 0; i < Math.min(10, rawData.length); i++) {
      if (rawData[i] && rawData[i].length > 1) { // Assuming a TB has at least a few columns
        headerRowIndex = i;
        break;
      }
    }
    
    const fileHeaders: string[] = rawData[headerRowIndex] || [];
    // Clean headers and make sure they are unique/strings
    const cleanHeaders = fileHeaders.map((h, i) => h ? String(h).trim() : `Column_${i}`);
    
    const dataObjects = rawData.slice(headerRowIndex + 1).map(row => {
      const obj: any = {};
      cleanHeaders.forEach((h, i) => {
        obj[h] = row[i];
      });
      return obj;
    });
    
    setHeaders(cleanHeaders);
    setParsedData(dataObjects);
    autoGuessMapping(cleanHeaders);
    setStep(3);
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    if (selectedFile.name.endsWith('.csv')) {
      setFileType('csv');
      Papa.parse(selectedFile, {
        header: true,
        skipEmptyLines: 'greedy',
        complete: (results) => {
          if (results.meta.fields) {
            setHeaders(results.meta.fields);
            setParsedData(results.data);
            autoGuessMapping(results.meta.fields);
            setStep(3);
          }
        },
        error: (error) => {
          toast.error('Failed to parse CSV: ' + error.message);
        }
      });
    } else if (selectedFile.name.match(/\.xlsx?$/i)) {
      setFileType('xlsx');
      const reader = new FileReader();
      reader.onload = (evt) => {
        try {
          const bstr = evt.target?.result;
          const wb = XLSX.read(bstr, { type: 'binary' });
          
          if (wb.SheetNames.length === 0) {
            toast.error('Workbook has no sheets.');
            return;
          }
          
          setWorkbook(wb);
          setSheetNames(wb.SheetNames);
          
          if (wb.SheetNames.length === 1) {
            setSelectedSheet(wb.SheetNames[0]);
            processSheetData(wb.Sheets[wb.SheetNames[0]]);
          } else {
            setStep(2);
          }
        } catch (err) {
          toast.error('Failed to read Excel file.');
        }
      };
      reader.readAsBinaryString(selectedFile);
    } else {
      toast.error('Unsupported file format. Please upload a .csv or .xlsx file.');
    }
  };

  const handleSheetSelect = () => {
    if (!workbook || !selectedSheet) return;
    const ws = workbook.Sheets[selectedSheet];
    processSheetData(ws);
  };

  const handleImport = () => {
    if (!mapping.ledger_name) {
      toast.error('Ledger Name mapping is required');
      return;
    }

    const parseNumber = (val: any) => {
      if (val === null || val === undefined || val === '') return 0;
      const num = parseFloat(val.toString().replace(/,/g, ''));
      return isNaN(num) ? 0 : num;
    };
    
    const rows: TBImportRow[] = [];
    let hasValidationError = false;
    let errorMsg = '';

    for (let i = 0; i < parsedData.length; i++) {
      const row = parsedData[i];
      
      // Check if row is completely empty
      const isRowEmpty = Object.values(row).every(v => v === null || v === undefined || v === '');
      if (isRowEmpty) continue;

      const ledgerName = row[mapping.ledger_name];
      
      if (!ledgerName || String(ledgerName).trim() === '') {
        hasValidationError = true;
        errorMsg = `Row ${i + 1} is missing a Ledger Name. Please correct the file and try again.`;
        break;
      }

      rows.push({
        ledger_code: mapping.ledger_code ? (row[mapping.ledger_code] ? String(row[mapping.ledger_code]) : null) : null,
        ledger_name: String(ledgerName).trim(),
        opening_balance: mapping.opening_balance ? parseNumber(row[mapping.opening_balance]) : 0,
        debit: mapping.debit ? parseNumber(row[mapping.debit]) : 0,
        credit: mapping.credit ? parseNumber(row[mapping.credit]) : 0,
        closing_balance: mapping.closing_balance ? parseNumber(row[mapping.closing_balance]) : 0,
      });
    }

    if (hasValidationError) {
      toast.error(errorMsg);
      return;
    }
    
    if (rows.length === 0) {
      toast.error("No valid data rows found to import.");
      return;
    }

    importMutation.mutate(rows);
  };

  const handleClose = () => {
    setFileType(null);
    setWorkbook(null);
    setSheetNames([]);
    setSelectedSheet('');
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
            {step === 1 ? 'Import Trial Balance' : step === 2 ? 'Select Sheet' : 'Map Columns'}
          </DialogTitle>
        </DialogHeader>
        
        {step === 1 && (
          <div className="space-y-4 py-4">
            <div className="flex items-center justify-center w-full">
              <label htmlFor="csv-file" className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-muted-foreground/30 rounded-lg cursor-pointer bg-muted/20 hover:bg-muted/40 transition-colors">
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <Upload className="w-8 h-8 mb-3 text-muted-foreground" />
                  <p className="mb-2 text-sm text-muted-foreground text-center px-4">
                    <span className="font-semibold text-foreground">Click to upload CSV or Excel</span>
                  </p>
                  <p className="text-xs text-muted-foreground">.csv, .xls, .xlsx</p>
                </div>
                <input 
                  id="csv-file" 
                  type="file" 
                  accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
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
              Your workbook contains multiple sheets. Please select the one containing the Trial Balance.
            </p>
            
            <div className="space-y-2">
              <label className="text-xs font-medium">Sheet Name</label>
              <Select value={selectedSheet} onValueChange={setSelectedSheet}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select a sheet..." />
                </SelectTrigger>
                <SelectContent>
                  {sheetNames.map(name => (
                    <SelectItem key={name} value={name}>
                      <span className="flex items-center gap-2">
                        <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
                        {name}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <DialogFooter className="mt-6">
              <Button type="button" variant="ghost" onClick={() => setStep(1)}>Cancel</Button>
              <Button 
                type="button" 
                onClick={handleSheetSelect}
                disabled={!selectedSheet}
              >
                Continue
              </Button>
            </DialogFooter>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4 py-4">
            <p className="text-sm text-muted-foreground mb-4">
              Map your {fileType?.toUpperCase()} columns to the Trial Balance fields.
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
                      <SelectItem value="_ignore">-- Ignore --</SelectItem>
                      {headers.map(h => (
                        <SelectItem key={h} value={h}>{h}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>

            <DialogFooter className="mt-6">
              <Button type="button" variant="ghost" onClick={() => {
                if (fileType === 'xlsx' && sheetNames.length > 1) {
                  setStep(2);
                } else {
                  setStep(1);
                }
              }}>Back</Button>
              <Button 
                type="button" 
                onClick={handleImport}
                disabled={importMutation.isPending || !mapping.ledger_name || mapping.ledger_name === '_ignore'}
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
