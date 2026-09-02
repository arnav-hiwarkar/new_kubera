import { ApiError } from '@/api/http'

/**
 * Turns a 429 into a message that tells the user when they can retry, or `null`
 * if this error is not a usable rate-limit response (callers then fall back to
 * their normal error text).
 *
 * The wait comes from the standard `Retry-After` header rather than a custom
 * body field: the app limiter sets it from the Redis bucket's TTL
 * (app/rate_limit.py) and nginx's edge limiter sets a fixed hint
 * (gateway/modes/app.conf). Nothing else about the limiter is exposed — not the
 * bucket, not the count, not which of the two limits was hit — so this cannot be
 * used to probe whether an account exists or how much budget is left.
 */
export function rateLimitMessage(err: unknown): string | null {
  if (!(err instanceof ApiError) || err.status !== 429) return null

  const raw = err.headers?.get('Retry-After')
  if (!raw) return null

  // `Number` rather than `parseInt`: Retry-After may legitimately be an
  // HTTP-date, and a half-parsed "Wed, 21 Oct..." must not become "21 minutes".
  const seconds = Number(raw)
  if (!Number.isFinite(seconds) || seconds <= 0) return null

  // Minutes, floored at 1 — a second-by-second countdown reads as pressure, and
  // "try again in 0 minutes" reads as a bug.
  const minutes = Math.max(1, Math.ceil(seconds / 60))
  return `Too many attempts. Please try again in ${minutes} minute${minutes > 1 ? 's' : ''}.`
}
