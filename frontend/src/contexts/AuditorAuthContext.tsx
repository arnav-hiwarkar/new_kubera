import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, setAuditorTokenGetter, setAuditorRefreshHandler, setAuditorLogoutHandler } from '@/lib/api';
import type { AuditorOut, TokenResponse, AuditorRegisterRequest } from '@/types/auth';

interface AuditorAuthContextValue {
  isAuthenticated: boolean;
  user: AuditorOut | null;
  login: (email: string, password: string) => Promise<void>;
  register: (data: AuditorRegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuditorAuthContext = createContext<AuditorAuthContextValue | null>(null);

export function AuditorAuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuditorOut | null>(null);
  const navigate = useNavigate();

  const handleLogout = useCallback(() => {
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
    navigate('/auditor/login', { replace: true });
  }, [navigate]);

  useEffect(() => {
    setAuditorTokenGetter(() => accessToken);
    
    setAuditorRefreshHandler(async () => {
      if (!refreshToken) return null;
      try {
        const response = await api.post<TokenResponse>('/auth/auditor/refresh', {
          refresh_token: refreshToken
        });
        setAccessToken(response.data.access_token);
        setRefreshToken(response.data.refresh_token);
        return response.data.access_token;
      } catch (error) {
        return null;
      }
    });

    setAuditorLogoutHandler(handleLogout);

    return () => {
      setAuditorTokenGetter(null);
      setAuditorRefreshHandler(null);
      setAuditorLogoutHandler(null);
    };
  }, [accessToken, refreshToken, handleLogout]);

  const login = useCallback(async (email: string, password: string) => {
    const loginResponse = await api.post<TokenResponse>('/auth/auditor/login', {
      email,
      password
    });
    
    setAccessToken(loginResponse.data.access_token);
    setRefreshToken(loginResponse.data.refresh_token);

    const tempToken = loginResponse.data.access_token;
    
    const meResponse = await api.get<AuditorOut>('/auth/auditor/me', {
      headers: { Authorization: `Bearer ${tempToken}` }
    });
    
    setUser(meResponse.data);
  }, []);

  const registerUser = useCallback(async (data: AuditorRegisterRequest) => {
    await api.post<AuditorOut>('/auth/auditor/register', data);
  }, []);

  return (
    <AuditorAuthContext.Provider
      value={{
        isAuthenticated: !!accessToken && !!user,
        user,
        login,
        register: registerUser,
        logout: handleLogout
      }}
    >
      {children}
    </AuditorAuthContext.Provider>
  );
}

export function useAuditorAuth() {
  const context = useContext(AuditorAuthContext);
  if (!context) {
    throw new Error('useAuditorAuth must be used within an AuditorAuthProvider');
  }
  return context;
}
