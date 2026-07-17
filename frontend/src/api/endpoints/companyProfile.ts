import { companyClient } from '@/api/clients/company'

/** Company profile (Indian Pvt Ltd). Mirrors the backend CompanyProfileOut. */
export interface CompanyProfile {
  id: string
  name: string
  legal_name: string | null
  cin: string | null
  pan: string | null
  gstin: string | null
  tan: string | null
  address_line1: string | null
  address_line2: string | null
  city: string | null
  state: string | null
  pincode: string | null
  contact_email: string | null
  contact_phone: string | null
  date_of_incorporation: string | null
  website: string | null
  industry: string | null
  profile_completed: boolean
  has_logo: boolean
}

export type CompanyProfileUpdate = Partial<
  Omit<CompanyProfile, 'id' | 'name' | 'profile_completed' | 'has_logo'>
> & {
  /** Set by the onboarding flow to mark the profile complete regardless of which optional fields were filled. */
  mark_completed?: boolean
}

export const companyProfileApi = {
  get: () => companyClient.get<CompanyProfile>('/api/v1/company/profile'),
  update: (body: CompanyProfileUpdate) =>
    companyClient.put<CompanyProfile>('/api/v1/company/profile', { body }),
  uploadLogo: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return companyClient.post<CompanyProfile>('/api/v1/company/profile/logo', { formData })
  },
  /** Fetch the logo as a Blob (auth header is attached by the client). */
  getLogoBlob: () =>
    companyClient.get<Blob>('/api/v1/company/profile/logo', { responseType: 'blob' }),
}
