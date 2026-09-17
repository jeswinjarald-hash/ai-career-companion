import { API_BASE_URL } from '../config/api'
import type { CandidateProfile } from './profileService'

export type AuthUser = {
  id: number
  full_name: string
  email: string
  created_at: string
}

export type AuthSession = {
  user: AuthUser
  profile: CandidateProfile | null
}

export class AuthApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'AuthApiError'
    this.status = status
  }
}

const errorMessage = (status: number, body: unknown): string => {
  if (status === 401) return 'Email or password is incorrect.'
  if (status === 409 && typeof body === 'object' && body !== null && 'detail' in body) {
    return String((body as { detail: unknown }).detail)
  }
  if (status === 422 && typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail
    if (Array.isArray(detail)) {
      const messages = detail.map((item) => typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : '').filter(Boolean)
      if (messages.length) return messages.join(' ')
    }
    if (typeof detail === 'string') return detail
  }
  return 'We could not complete that request. Please try again.'
}

const request = async (path: string, options?: RequestInit): Promise<Response> => {
  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    })
  } catch {
    throw new AuthApiError(0, "We couldn't connect to the authentication service. Please try again.")
  }
}

const parseSession = async (response: Response): Promise<AuthSession> => {
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new AuthApiError(response.status, errorMessage(response.status, body))
  return body as AuthSession
}

export const registerAccount = async (payload: {
  full_name: string
  email: string
  password: string
  confirm_password: string
}): Promise<AuthSession> => parseSession(await request('/api/auth/register', { method: 'POST', body: JSON.stringify(payload) }))

export const login = async (payload: { email: string; password: string }): Promise<AuthSession> =>
  parseSession(await request('/api/auth/login', { method: 'POST', body: JSON.stringify(payload) }))

export const logout = async (): Promise<void> => {
  await request('/api/auth/logout', { method: 'POST' })
}

export const getCurrentSession = async (): Promise<AuthSession | null> => {
  const response = await request('/api/auth/me', { method: 'GET' })
  if (response.status === 401) return null
  return parseSession(response)
}
