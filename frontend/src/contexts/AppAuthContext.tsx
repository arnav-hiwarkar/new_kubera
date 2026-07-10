import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, setAppTokenGetter, setAppRefreshHandler, setAppLogoutHandler } from '@/lib/api';
import type { CompanyUserOut, TokenResponse, UserRole } from '@/types/auth';

interface AppAuthContextValue {
  isAuthenticated: boolean;
  user: CompanyUserOut | null;
  role: UserRole | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AppAuthContext = createContext<AppAuthContextValue | null>(null);

export function AppAuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [user, setUser] = useState<CompanyUserOut | null>(null);
  const navigate = useNavigate();

  const handleLogout = useCallback(() => {
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
    navigate('/app/login', { replace: true });
  }, [navigate]);

  useEffect(() => {
    setAppTokenGetter(() => accessToken);
    
    setAppRefreshHandler(async () => {
      if (!refreshToken) return null;
      try {
        const response = await api.post<TokenResponse>('/auth/company/refresh', {
          refresh_token: refreshToken
        });
        setAccessToken(response.data.access_token);
        setRefreshToken(response.data.refresh_token);
        return response.data.access_token;
      } catch (error) {
        return null;
      }
    });

    setAppLogoutHandler(handleLogout);

    return () => {
      setAppTokenGetter(null);
      setAppRefreshHandler(null);
      setAppLogoutHandler(null);
    };
  }, [accessToken, refreshToken, handleLogout]);

  const login = useCallback(async (email: string, password: string) => {
    const loginResponse = await api.post<TokenResponse>('/auth/company/login', {
      email,
      password
    });
    
    setAccessToken(loginResponse.data.access_token);
    setRefreshToken(loginResponse.data.refresh_token);

    // Using a temporary token getter just for this request since state update is async
    const tempToken = loginResponse.data.access_token;
    
    const meResponse = await api.get<CompanyUserOut>('/auth/company/me', {
      headers: { Authorization: `Bearer ${tempToken}` }
    });
    
    setUser(meResponse.data);
  }, []);

  return (
    <AppAuthContext.Provider
      value={{
        isAuthenticated: !!accessToken && !!user,
        user,
        role: user?.role ?? null,
        login,
        logout: handleLogout
      }}
    >
      {children}
    </AppAuthContext.Provider>
  );
}

export function useAppAuth() {
  const context = useContext(AppAuthContext);
  if (!context) {
    throw new Error('useAppAuth must be used within an AppAuthProvider');
  }
  return context;
}
