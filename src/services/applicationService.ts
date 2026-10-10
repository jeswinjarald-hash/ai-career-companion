import { apiDetailMessage, apiFetch } from '../config/api'

// Mirrors backend/app/schemas/application.py — keep the two in sync.
export type ApplicationStatus =
  | 'saved' | 'planning' | 'applied' | 'under_review' | 'shortlisted'
  | 'interview_scheduled' | 'interview_completed' | 'offer' | 'rejected' | 'withdrawn'
export type ApplicationSource = 'dataset' | 'manual'
export type InterviewStatus = 'scheduled' | 'completed' | 'cancelled'
export type ApplicationSort = 'updated_desc' | 'created_desc' | 'deadline_asc' | 'applied_desc' | 'company_asc'
export type ReminderType = 'deadline' | 'interview' | 'follow_up' | 'pending'

export const APPLICATION_STATUSES: ApplicationStatus[] = [
  'saved', 'planning', 'applied', 'under_review', 'shortlisted',
  'interview_scheduled', 'interview_completed', 'offer', 'rejected', 'withdrawn',
]

export type Application = {
  id: number
  source: ApplicationSource
  job_id: string | null
  company: string
  job_title: string
  employment_type: string | null
  location: string | null
  work_mode: string | null
  job_description: string | null
  status: ApplicationStatus
  status_updated_at: string
  applied_date: string | null
  deadline: string | null
  interview_at: string | null
  interview_status: InterviewStatus | null
  follow_up_date: string | null
  notes: string | null
  customization_id: number | null
  interview_preparation_id: number | null
  created_at: string
  updated_at: string
  // Computed by the backend from `status` (offer/rejected/withdrawn are completed).
  is_active: boolean
}

type TrackerFields = {
  applied_date?: string | null
  deadline?: string | null
  // Must carry a timezone offset — the backend rejects naive timestamps.
  interview_at?: string | null
  interview_status?: InterviewStatus | null
  follow_up_date?: string | null
  notes?: string | null
  customization_id?: number | null
  interview_preparation_id?: number | null
}

type ManualOpportunityFields = {
  employment_type?: string | null
  location?: string | null
  work_mode?: string | null
  job_description?: string | null
}

// Dataset applications send only job_id: the backend snapshots company/title/etc.
export type DatasetApplicationCreate = TrackerFields & { job_id: string; status?: ApplicationStatus }
export type ManualApplicationCreate = TrackerFields & ManualOpportunityFields & { company: string; job_title: string; status?: ApplicationStatus }
export type ApplicationUpdate = TrackerFields & ManualOpportunityFields & { status?: ApplicationStatus; company?: string; job_title?: string }

export type ApplicationFilters = {
  status?: ApplicationStatus[]
  q?: string
  active?: boolean
  deadline_from?: string
  deadline_to?: string
  applied_from?: string
  applied_to?: string
  sort?: ApplicationSort
}

export type ApplicationSummary = {
  total_applications: number
  active_applications: number
  completed_applications: number
  upcoming_deadlines: number
  interviews_scheduled: number
  offers_received: number
  rejected_applications: number
  upcoming_deadline_window_days: number
  status_counts: Record<ApplicationStatus, number>
}

export type ApplicationReminder = {
  type: ReminderType
  application_id: number
  company: string
  job_title: string
  status: ApplicationStatus
  due_date: string
  due_at: string | null
  days_until: number
  overdue: boolean
  message: string
}

export type ApplicationReminders = { window_days: number; today: string; reminders: ApplicationReminder[] }

export class ApplicationApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApplicationApiError'
    this.status = status
  }
}

const request = async <T>(path: string, options?: RequestInit): Promise<T> => {
  let response: Response
  try {
    response = await apiFetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    })
  } catch {
    throw new ApplicationApiError(0, "We couldn't connect to the application tracker. Please try again.")
  }
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApplicationApiError(response.status, apiDetailMessage(body, 'We could not complete that request.', response.status))
  return body as T
}

const filterQuery = (filters: ApplicationFilters): string => {
  const params = new URLSearchParams()
  filters.status?.forEach((status) => params.append('status', status))
  if (filters.q?.trim()) params.set('q', filters.q.trim())
  if (filters.active !== undefined) params.set('active', String(filters.active))
  for (const key of ['deadline_from', 'deadline_to', 'applied_from', 'applied_to', 'sort'] as const) {
    const value = filters[key]
    if (value) params.set(key, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ''
}

export const createApplicationFromJob = (payload: DatasetApplicationCreate) =>
  request<Application>('/api/applications', { method: 'POST', body: JSON.stringify(payload) })

export const createManualApplication = (payload: ManualApplicationCreate) =>
  request<Application>('/api/applications', { method: 'POST', body: JSON.stringify(payload) })

export const listApplications = (filters: ApplicationFilters = {}) =>
  request<Application[]>(`/api/applications${filterQuery(filters)}`)

export const getApplication = async (applicationId: number): Promise<Application | null> => {
  try {
    return await request<Application>(`/api/applications/${applicationId}`)
  } catch (error: unknown) {
    if (error instanceof ApplicationApiError && error.status === 404) return null
    throw error
  }
}

export const updateApplication = (applicationId: number, payload: ApplicationUpdate) =>
  request<Application>(`/api/applications/${applicationId}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteApplication = (applicationId: number) =>
  request<void>(`/api/applications/${applicationId}`, { method: 'DELETE' })

export const getApplicationSummary = () => request<ApplicationSummary>('/api/applications/summary')

export const getApplicationReminders = (days = 7) => request<ApplicationReminders>(`/api/applications/reminders?days=${days}`)

// There is no job_id filter on the list endpoint; a student's tracker is small, so
// the tracked application for one canonical job is found from the full list.
export const findApplicationForJob = async (jobId: string): Promise<Application | null> =>
  (await listApplications()).find((application) => application.job_id === jobId) ?? null
