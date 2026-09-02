import { describe, it, expect } from 'vitest'
import { ApiError } from '@/api/http'
import { rateLimitMessage } from '@/api/rateLimit'

function err(status: number, headers: Record<string, string> = {}) {
  return new ApiError(status, 'Too many attempts. Please try again later.', undefined, new Headers(headers))
}

describe('rateLimitMessage', () => {
  it('renders the wait in whole minutes, rounded up', () => {
    expect(rateLimitMessage(err(429, { 'Retry-After': '900' }))).toBe(
      'Too many attempts. Please try again in 15 minutes.',
    )
    expect(rateLimitMessage(err(429, { 'Retry-After': '61' }))).toBe(
      'Too many attempts. Please try again in 2 minutes.',
    )
  })

  it('says "minute", singular, for exactly one', () => {
    expect(rateLimitMessage(err(429, { 'Retry-After': '60' }))).toBe(
      'Too many attempts. Please try again in 1 minute.',
    )
  })

  it('floors a sub-minute wait at one minute rather than saying "0 minutes"', () => {
    expect(rateLimitMessage(err(429, { 'Retry-After': '1' }))).toBe(
      'Too many attempts. Please try again in 1 minute.',
    )
  })

  // --- the paths that must NOT produce a countdown -------------------------

  it('declines a 429 with no Retry-After', () => {
    // nginx's edge limiter and any intermediary can return a bare 429; the
    // caller then falls back to the server's own message.
    expect(rateLimitMessage(err(429))).toBeNull()
  })

  it.each([
    ['unparseable', 'soon'],
    ['an HTTP-date, which we do not render', 'Wed, 21 Oct 2015 07:28:00 GMT'],
    ['partially numeric', '12 minutes'],
    ['empty', ''],
    ['zero', '0'],
    ['negative', '-2'],
  ])('declines a Retry-After that is %s', (_label, value) => {
    // The failure being guarded against is "Please try again in NaN minutes."
    expect(rateLimitMessage(err(429, { 'Retry-After': value }))).toBeNull()
  })

  it.each([400, 401, 403, 500])('ignores a %i, even with a Retry-After', (status) => {
    // A rate-limit notice must never swallow "Invalid credentials".
    expect(rateLimitMessage(err(status, { 'Retry-After': '300' }))).toBeNull()
  })

  it('ignores errors that are not ApiError, and non-errors', () => {
    expect(rateLimitMessage(new Error('network down'))).toBeNull()
    expect(rateLimitMessage(undefined)).toBeNull()
    expect(rateLimitMessage(null)).toBeNull()
    expect(rateLimitMessage({ status: 429 })).toBeNull()
  })

  it('survives an ApiError carrying no headers at all', () => {
    expect(rateLimitMessage(new ApiError(429, 'Too many attempts.'))).toBeNull()
  })
})
