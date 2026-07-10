export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  role: string | null;
  full_name: string | null;
}

export interface CompanyUserOut {
  id: string;
  company_id: string;
  email: string;
  role: 'admin' | 'manager' | 'employee';
  manager_id: string | null;
  full_name: string;
  designation: string | null;
  department: string | null;
  is_active: boolean;
}

export interface AuditorOut {
  id: string;
  email: string;
  name: string;
}

export interface AuditorRegisterRequest {
  email: string;
  password: string;
  name: string;
}

export type UserRole = 'admin' | 'manager' | 'employee';
