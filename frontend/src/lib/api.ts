import axios from 'axios';
import type { AxiosError, InternalAxiosRequestConfig } from 'axios';

/**
 * Callback types for the auth integration.
 * Each auth context (company or auditor) registers its own handlers on mount.
 */
type TokenGetter = () => string | null;
type RefreshHandler = () => Promise<string | null>;
type LogoutHandler = () => void;

let getToken: TokenGetter | null = null;
let refreshTokenFn: RefreshHandler | null = null;
let logoutFn: LogoutHandler | null = null;

/**
 * Register a function that returns the current access token.
 * Called by auth contexts on mount.
 */
export function setTokenGetter(fn: TokenGetter | null): void {
  getToken = fn;
}

/**
 * Register a function that performs a token refresh and returns the new access token.
 * Called by auth contexts on mount.
 */
export function setRefreshHandler(fn: RefreshHandler | null): void {
  refreshTokenFn = fn;
}

/**
 * Register a function that performs logout (clears state, navigates away).
 * Called by auth contexts on mount.
 */
export function setLogoutHandler(fn: LogoutHandler | null): void {
  logoutFn = fn;
}

/**
 * Configured Axios instance for all API calls.
 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

/**
 * Request interceptor — attach Bearer token if available.
 */
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getToken?.();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error),
);

/**
 * Track whether a refresh is in-flight to avoid concurrent refresh attempts.
 */
let isRefreshing = false;
let refreshPromise: Promise<string | null> | null = null;

/**
 * Response interceptor — on 401, attempt silent token refresh.
 *
 * If a refresh is already in-flight, we queue behind it to avoid
 * multiple concurrent refresh calls.
 *
 * If refresh succeeds, the original request is retried with the new token.
 * If refresh fails, logout is called and the error is rejected.
 */
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Only attempt refresh on 401, if we haven't already retried,
    // and if a refresh handler is registered.
    if (
      error.response?.status !== 401 ||
      originalRequest._retry ||
      !refreshTokenFn
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    // If a refresh is already in progress, wait for it.
    if (isRefreshing && refreshPromise) {
      try {
        const newToken = await refreshPromise;
        if (newToken) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        }
      } catch {
        logoutFn?.();
        return Promise.reject(error);
      }
    }

    // Start a new refresh.
    isRefreshing = true;
    refreshPromise = refreshTokenFn();

    try {
      const newToken = await refreshPromise;
      if (newToken) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      }
      // Refresh returned null — token couldn't be refreshed.
      logoutFn?.();
      return Promise.reject(error);
    } catch {
      logoutFn?.();
      return Promise.reject(error);
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  },
);
