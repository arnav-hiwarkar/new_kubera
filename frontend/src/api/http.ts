import type { TokenStorage } from '@/auth/tokenStorage'

/** Base URL for the API. In dev, Vite proxies `/api` to the backend (see vite.config.ts). */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export interface RequestOptions {
  query?: Record<string, string | number | boolean | undefined | null>
  /** JSON body. Ignored if `formData` is set. */
  body?: unknown
  /** For multipart uploads (imports, document uploads). */
  formData?: FormData
  signal?: AbortSignal
  /** Set for file downloads — returns a Blob instead of parsed JSON. */
  responseType?: 'json' | 'blob'
}

/**
 * An identity-scoped adapter. Each identity (company, auditor) provides its own
 * token storage and its own refresh endpoint, so the two clients never share
 * credentials or refresh paths.
 */
export interface AuthAdapter {
  storage: TokenStorage
  /** Path to this identity's refresh endpoint, e.g. `/api/v1/auth/company/refresh`. */
  refreshPath: string
  /** Called when refresh fails / no session — hooks into the auth store to force logout. */
  onAuthFailure: () => void
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(API_BASE_URL + path, window.location.origin)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v))
    }
  }
  return url.toString().replace(window.location.origin, '')
}

async function parseError(res: Response): Promise<ApiError> {
  let detail: unknown
  let message = `Request failed with status ${res.status}`
  try {
    const data = await res.json()
    detail = data?.detail ?? data
    if (typeof data?.detail === 'string') message = data.detail
    else if (Array.isArray(data?.detail) && data.detail[0]?.msg) message = data.detail[0].msg
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, message, detail)
}

export class HttpClient {
  constructor(private readonly auth: AuthAdapter) {}

  /** Attempt a one-time refresh using this identity's refresh token. */
  private async tryRefresh(): Promise<boolean> {
    const tokens = this.auth.storage.get()
    if (!tokens?.refreshToken) return false
    try {
      const res = await fetch(buildUrl(this.auth.refreshPath), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: tokens.refreshToken }),
      })
      if (!res.ok) return false
      const data = (await res.json()) as { access_token: string; refresh_token: string }
      this.auth.storage.set({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
      })
      return true
    } catch {
      return false
    }
  }

  private async execute(
    method: string,
    path: string,
    opts: RequestOptions,
    isRetry = false,
  ): Promise<Response> {
    const tokens = this.auth.storage.get()
    const headers: Record<string, string> = {}
    if (tokens?.accessToken) headers.Authorization = `Bearer ${tokens.accessToken}`

    let body: BodyInit | undefined
    if (opts.formData) {
      body = opts.formData // browser sets multipart boundary
    } else if (opts.body !== undefined) {
      headers['Content-Type'] = 'application/json'
      body = JSON.stringify(opts.body)
    }

    const res = await fetch(buildUrl(path, opts.query), {
      method,
      headers,
      body,
      signal: opts.signal,
    })

    // Single refresh-and-retry on 401 for authenticated requests.
    if (res.status === 401 && !isRetry && tokens?.accessToken) {
      const refreshed = await this.tryRefresh()
      if (refreshed) return this.execute(method, path, opts, true)
      this.auth.onAuthFailure()
    }
    return res
  }

  async request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    const res = await this.execute(method, path, opts)
    if (!res.ok) throw await parseError(res)
    if (opts.responseType === 'blob') return (await res.blob()) as T
    if (res.status === 204) return undefined as T
    const text = await res.text()
    return (text ? JSON.parse(text) : undefined) as T
  }

  get<T>(path: string, opts?: RequestOptions) {
    return this.request<T>('GET', path, opts)
  }
  post<T>(path: string, opts?: RequestOptions) {
    return this.request<T>('POST', path, opts)
  }
  patch<T>(path: string, opts?: RequestOptions) {
    return this.request<T>('PATCH', path, opts)
  }
  put<T>(path: string, opts?: RequestOptions) {
    return this.request<T>('PUT', path, opts)
  }
  delete<T>(path: string, opts?: RequestOptions) {
    return this.request<T>('DELETE', path, opts)
  }
}
