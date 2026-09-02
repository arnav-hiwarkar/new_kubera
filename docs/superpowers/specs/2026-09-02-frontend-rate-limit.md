# Feature: Rate Limit UI Feedback

## 1. Context & Motivation
Following the implementation of strict rate limits across authentication and activation endpoints (KUB-003), legitimate users who accidentally hit the limit receive a generic error message ("Login failed" or "Too many attempts"). This creates a poor user experience, as users are not informed of how long they must wait before trying again. The goal is to surface the remaining lockout time in the frontend in a secure, non-exploitable way.

## 2. Architecture & Design
- **Backend Transmission (Non-Exploitable):**
  - Rather than returning a custom JSON shape that could be abused or misinterpreted, the backend will return the remaining time via the standard HTTP `Retry-After` header. This is the internet-standard mechanism for communicating rate limit resets.
  - In `app/rate_limit.py`, when a rate limit is exceeded, we query the Redis key's Time-To-Live (TTL) using `await _redis().ttl(key)` and append `headers={"Retry-After": str(ttl)}` to the `HTTPException(429)`.
- **Frontend Parsing:**
  - In `frontend/src/api/http.ts`, the `parseError` function has been augmented to capture the raw `res.headers` and attach them to the thrown `ApiError` class.
  - The parsing lives in one place, `frontend/src/api/rateLimit.ts`. `rateLimitMessage(err)` returns the notice or `null`, and the four forms (`CompanyLogin.tsx`, `AuditorLogin.tsx`, `AuditorRegister.tsx`, `CompanyActivate.tsx`) each read `rateLimitMessage(err) ?? <their existing fallback>`. Four copies of the same header arithmetic would have been four places for the `NaN` and `0 minutes` bugs to hide.
- **User Interface:**
  - If a `Retry-After` header parses to a positive number of seconds, the frontend rounds up to minutes (floored at 1) and sets `"Too many attempts. Please try again in X minute(s)."`.
  - Anything else — header absent, an HTTP-date, unparseable, zero, negative, or a non-429 — returns `null` and the form keeps its own error text. `"Invalid credentials"` must never be replaced by a rate-limit notice, and `"try again in NaN minutes"` must never be reachable.
  - This seamlessly integrates with the existing inline `<formError>` banner.

## 3. Trade-offs & Security
- Using the standard `Retry-After` header avoids leaking custom metadata structures in error responses, reducing the attack surface.
- Converting seconds into minutes on the frontend prevents users from obsessing over a ticking second-by-second countdown and keeps the UI simple and static.
- The header is the *only* thing exposed. Not the count, not the bucket, not which of the two limits (per-account or per-IP) rejected the request — so the notice cannot be used to probe whether an account exists or how much budget an attacker has left.
- The edge limiter answers before the application does. `gateway/modes/app.conf` therefore renders its own 429 as the same `{"detail": ...}` JSON with a fixed `Retry-After: 60`; with nginx's stock HTML error page the user would see "Request failed with status 429" instead of the notice.

## 4. Final Status
The backend appends `Retry-After` from the Redis TTL, falling back to the full window when Redis reports -1/-2 rather than emitting `Retry-After: 0`. The four forms route their 429 handling through `rateLimitMessage`. Covered by `frontend/src/api/rateLimit.test.ts` (16 cases, mostly the paths that must *not* produce a countdown) and the four component tests that drive a real 429 through the mounted route table.
