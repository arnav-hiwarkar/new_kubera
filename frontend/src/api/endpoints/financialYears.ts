import { companyClient } from '@/api/clients/company'
import type { FinancialYearCreate, FinancialYearResponse } from '@/api/types'

export const financialYearsApi = {
  list: () => companyClient.get<FinancialYearResponse[]>('/api/v1/financial-years'),
  create: (body: FinancialYearCreate) =>
    companyClient.post<FinancialYearResponse>('/api/v1/financial-years', { body }),
  close: (id: string) =>
    companyClient.post<FinancialYearResponse>(`/api/v1/financial-years/${id}/close`),
  reopen: (id: string) =>
    companyClient.post<FinancialYearResponse>(`/api/v1/financial-years/${id}/reopen`),
}
