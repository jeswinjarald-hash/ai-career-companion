import { API_BASE_URL } from '../config/api'

export type CandidateProfile = {
  id: number
  full_name: string
  email: string
  education: string | null
  degree: string | null
  specialization: string | null
  experience_level: string | null
  career_interests: string[]
  target_roles: string[]
  skills: string[]
  career_goals: string | null
  created_at: string
  updated_at: string
}

export type CandidateProfilePayload = Omit<CandidateProfile, 'id' | 'created_at' | 'updated_at'>

export class ProfileApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ProfileApiError'
    this.status = status
  }
}

const errorMessage = (status: number, body: unknown): string => {
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 404) return 'Profile not found.'
  if (status === 409) return 'A profile with this email already exists.'
  if (status === 422 && typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail?: unknown }).detail
    if (Array.isArray(detail)) {
      const messages = detail.map((item) => typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : '').filter(Boolean)
      if (messages.some((message) => message.toLowerCase().includes('email'))) return 'Please enter a valid email address.'
      if (messages.some((message) => message.toLowerCase().includes('full_name'))) return 'Full name is required.'
      return messages.join(' ')
    }
  }
  return 'We could not save your profile. Please try again.'
}

const request = async <T>(path: string, options?: RequestInit): Promise<T> => {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    })
  } catch {
    throw new ProfileApiError(0, "We couldn't connect to the profile service. Please try again.")
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ProfileApiError(response.status, errorMessage(response.status, body))
  return body as T
}

export const getProfile = (profileId: number) => request<CandidateProfile>(`/api/profiles/${profileId}`)

export const createProfile = (payload: CandidateProfilePayload) =>
  request<CandidateProfile>('/api/profiles', { method: 'POST', body: JSON.stringify(payload) })

export const updateProfile = (profileId: number, payload: CandidateProfilePayload) =>
  request<CandidateProfile>(`/api/profiles/${profileId}`, { method: 'PATCH', body: JSON.stringify(payload) })