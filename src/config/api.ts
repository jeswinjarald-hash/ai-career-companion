// Same hostname as the frontend dev server (both `localhost`) so the auth session
// cookie is same-site and browsers actually attach it to cross-port fetch requests.
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

// Fired when an authenticated API call comes back 401 (session expired, revoked, or
// signed out in another tab). App listens for it and returns to the sign-in screen
// instead of leaving each page showing a raw "Authentication required." error.
export const SESSION_EXPIRED_EVENT = 'ai-career:session-expired'

// Credentialed fetch for every authenticated feature service. Network failures are
// left to the caller (each service has its own wording); only the 401 signal is shared.
export const apiFetch = async (path: string, init?: RequestInit): Promise<Response> => {
  const response = await fetch(path.startsWith('http') ? path : `${API_BASE_URL}${path}`, { ...init, credentials: 'include' })
  if (response.status === 401) window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
  return response
}

// Generation requests can run two bounded LLM calls (initial + one repair, each capped
// by the backend LLM_TIMEOUT_SECONDS — 60s in the current .env, so ~120s worst case)
// plus deterministic work; past this the client stops waiting instead of spinning
// forever. Aborting does not cancel server work, so callers must say so honestly.
export const GENERATION_TIMEOUT_MS = 150_000

export class RequestTimeoutError extends Error {}

export const fetchWithTimeout = async (path: string, init: RequestInit, timeoutMs: number): Promise<Response> => {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await apiFetch(path, { ...init, signal: controller.signal })
  } catch (error: unknown) {
    if (controller.signal.aborted) throw new RequestTimeoutError('timeout')
    throw error
  } finally {
    window.clearTimeout(timer)
  }
}

// FastAPI returns a string `detail` for HTTPExceptions but a list of Pydantic error
// objects for 422 validation failures — turn the latter into readable text instead
// of showing raw JSON or "[object Object]". Server errors never surface internals.
export const apiDetailMessage = (body: unknown, fallback: string, status?: number): string => {
  if (status !== undefined && status >= 500) return 'Something went wrong on the server. Please try again in a moment.'
  if (!body || typeof body !== 'object' || !('detail' in body)) return fallback
  const detail = (body as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (!item || typeof item !== 'object') return ''
      const { msg, loc } = item as { msg?: unknown; loc?: unknown }
      const field = Array.isArray(loc) ? loc.filter((part) => part !== 'body' && part !== 'query' && typeof part === 'string').join('.') : ''
      const text = typeof msg === 'string' ? msg.replace(/^Value error, /, '') : ''
      return field && text ? `${field.replace(/_/g, ' ')}: ${text}` : text
    }).filter(Boolean)
    if (messages.length > 0) return messages.join(' ')
  }
  return fallback
}
