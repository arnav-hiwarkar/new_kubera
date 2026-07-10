import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import CompanyLoginPage from '../pages/app/LoginPage';
import { AppAuthProvider } from '../contexts/AppAuthContext';
import { api } from '../lib/api';

vi.mock('../lib/api', () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
  },
  setTokenGetter: vi.fn(),
  setRefreshHandler: vi.fn(),
  setLogoutHandler: vi.fn(),
}));

const renderWithProviders = (ui: React.ReactElement) => {
  return render(
    <BrowserRouter>
      <AppAuthProvider>
        {ui}
      </AppAuthProvider>
    </BrowserRouter>
  );
};

describe('Auth Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login page correctly', () => {
    renderWithProviders(<CompanyLoginPage />);
    expect(screen.getByText('Company Portal')).toBeInTheDocument();
    expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Sign in/i })).toBeInTheDocument();
  });

  it('shows validation errors for empty fields', async () => {
    renderWithProviders(<CompanyLoginPage />);
    const button = screen.getByRole('button', { name: /Sign in/i });
    fireEvent.click(button);
    
    await waitFor(() => {
      expect(screen.getByText(/Email is required/i)).toBeInTheDocument();
      expect(screen.getByText(/Password is required/i)).toBeInTheDocument();
    });
  });

  it('calls login API on valid submission', async () => {
    // Mock successful login and me endpoints
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { access_token: 'test-token', refresh_token: 'test-refresh' }
    });
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      data: { id: '1', role: 'employee', full_name: 'Test User' }
    });

    renderWithProviders(<CompanyLoginPage />);
    
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'test@company.com' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'password123' } });
    
    fireEvent.click(screen.getByRole('button', { name: /Sign in/i }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/company/login', {
        email: 'test@company.com',
        password: 'password123'
      });
    });
  });

  it('handles server errors', async () => {
    (api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Invalid credentials'));

    renderWithProviders(<CompanyLoginPage />);
    
    fireEvent.change(screen.getByLabelText(/Email/i), { target: { value: 'test@company.com' } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'password123' } });
    
    fireEvent.click(screen.getByRole('button', { name: /Sign in/i }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid credentials/i)).toBeInTheDocument();
    });
  });
});
