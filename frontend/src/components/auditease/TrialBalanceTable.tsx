
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { TrialBalanceAccountResponse } from '@/types/auditease';

interface TrialBalanceTableProps {
  tbAccounts: TrialBalanceAccountResponse[];
  isLoading: boolean;
  isReadOnly?: boolean;
}

export function TrialBalanceTable({ tbAccounts, isLoading }: TrialBalanceTableProps) {
  return (
    <div className="rounded-md border border-border bg-card flex-1 overflow-hidden flex flex-col h-full w-full">
      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader className="bg-muted/50 sticky top-0 z-10 shadow-sm">
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[100px]">Code</TableHead>
              <TableHead className="min-w-[200px]">Ledger Name</TableHead>
              <TableHead className="min-w-[150px]">Top Group</TableHead>
              <TableHead className="min-w-[150px]">Parent Group</TableHead>
              <TableHead className="min-w-[150px]">Mapped Group</TableHead>
              <TableHead className="text-right w-[120px]">Opening</TableHead>
              <TableHead className="text-right w-[120px]">Debit</TableHead>
              <TableHead className="text-right w-[120px]">Credit</TableHead>
              <TableHead className="text-right w-[120px]">Closing</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8 text-muted-foreground h-32">
                  Loading trial balance...
                </TableCell>
              </TableRow>
            ) : tbAccounts.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-8 text-muted-foreground h-32">
                  No accounts found.
                </TableCell>
              </TableRow>
            ) : (
              tbAccounts.map((acc) => (
                <TableRow key={acc.id} className="hover:bg-muted/30 transition-colors">
                  <TableCell className="font-mono text-xs text-muted-foreground truncate">{acc.ledger_code || '—'}</TableCell>
                  <TableCell className="font-medium truncate">{acc.ledger_name}</TableCell>
                  <TableCell className="text-muted-foreground text-sm truncate">{acc.top_group_name || '—'}</TableCell>
                  <TableCell className="text-muted-foreground text-sm truncate">{acc.parent_group_name || '—'}</TableCell>
                  <TableCell className="text-muted-foreground text-sm truncate">{acc.mapped_group_name || '—'}</TableCell>
                  <TableCell className="text-right">{acc.opening_balance.toLocaleString()}</TableCell>
                  <TableCell className="text-right text-destructive">{acc.debit.toLocaleString()}</TableCell>
                  <TableCell className="text-right text-green-500">{acc.credit.toLocaleString()}</TableCell>
                  <TableCell className="text-right font-medium">{acc.closing_balance.toLocaleString()}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
