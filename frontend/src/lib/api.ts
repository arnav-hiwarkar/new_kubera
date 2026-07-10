import axios from 'axios';
import type { AxiosError, InternalAxiosRequestConfig } from 'axios';

/**
 * Callback types for the auth integration.
 * Each auth context (company or auditor) registers its own handlers on mount.
 */
type TokenGetter = () => string | null;
type RefreshHandler = () => Promise<string | null>;
type LogoutHandler = () => void;

let getAppToken: TokenGetter | null = null;
let getAuditorToken: TokenGetter | null = null;
let appRefreshFn: RefreshHandler | null = null;
let auditorRefreshFn: RefreshHandler | null = null;
let appLogoutFn: LogoutHandler | null = null;
let auditorLogoutFn: LogoutHandler | null = null;

export function setAppTokenGetter(fn: TokenGetter | null): void { getAppToken = fn; }
export function setAuditorTokenGetter(fn: TokenGetter | null): void { getAuditorToken = fn; }

export function setAppRefreshHandler(fn: RefreshHandler | null): void { appRefreshFn = fn; }
export function setAuditorRefreshHandler(fn: RefreshHandler | null): void { auditorRefreshFn = fn; }

export function setAppLogoutHandler(fn: LogoutHandler | null): void { appLogoutFn = fn; }
export function setAuditorLogoutHandler(fn: LogoutHandler | null): void { auditorLogoutFn = fn; }

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
    const isAuditorRoute = config.url?.startsWith('/auditor') || config.url?.startsWith('/auth/auditor');
    const token = isAuditorRoute ? getAuditorToken?.() : getAppToken?.();
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

    const isAuditorRoute = originalRequest.url?.startsWith('/auditor') || originalRequest.url?.startsWith('/auth/auditor');
    const refreshFn = isAuditorRoute ? auditorRefreshFn : appRefreshFn;
    const logoutHandler = isAuditorRoute ? auditorLogoutFn : appLogoutFn;

    if (
      error.response?.status !== 401 ||
      originalRequest._retry ||
      !refreshFn
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    if (isRefreshing && refreshPromise) {
      try {
        const newToken = await refreshPromise;
        if (newToken) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        }
      } catch {
        logoutHandler?.();
        return Promise.reject(error);
      }
    }

    isRefreshing = true;
    refreshPromise = refreshFn();

    try {
      const newToken = await refreshPromise;
      if (newToken) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      }
      logoutHandler?.();
      return Promise.reject(error);
    } catch {
      logoutHandler?.();
      return Promise.reject(error);
    } finally {
      isRefreshing = false;
      refreshPromise = null;
    }
  },
);
