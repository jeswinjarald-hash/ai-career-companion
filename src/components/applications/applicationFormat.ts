import type { ApplicationStatus, InterviewStatus, ReminderType } from '../../services/applicationService'

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  saved: 'Saved',
  planning: 'Planning to Apply',
  applied: 'Applied',
  under_review: 'Under Review',
  shortlisted: 'Shortlisted',
  interview_scheduled: 'Interview Scheduled',
  interview_completed: 'Interview Completed',
  offer: 'Offer Received',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
}

// Reuses the existing `skill-status` tones: green = good outcome, amber = in
// progress, red = closed without an offer.
export const STATUS_TONE: Record<ApplicationStatus, string> = {
  saved: 'adequate', planning: 'adequate', applied: 'adequate', under_review: 'adequate',
  shortlisted: 'strong', interview_scheduled: 'strong', interview_completed: 'strong',
  offer: 'strong', rejected: 'missing', withdrawn: 'missing',
}

export const INTERVIEW_STATUS_LABEL: Record<InterviewStatus, string> = { scheduled: 'Scheduled', completed: 'Completed', cancelled: 'Cancelled' }

export const REMINDER_LABEL: Record<ReminderType, string> = {
  deadline: 'Application deadline',
  interview: 'Interview',
  follow_up: 'Follow-up',
  pending: 'Awaiting response',
}

export const EMPLOYMENT_TYPE_SUGGESTIONS = ['Internship', 'Entry Level', 'Graduate Role', 'Trainee', 'Apprenticeship']
export const WORK_MODES = ['On-site', 'Hybrid', 'Remote']

export const browserTimeZone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone || 'your local time zone'

// Calendar dates ("YYYY-MM-DD") are formatted from their parts so they are never
// shifted by a timezone conversion.
export const formatDate = (value: string | null): string => {
  if (!value) return ''
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return value
  return new Date(year, month - 1, day).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

// Every backend timestamp is stored in UTC, but some existing (pre-M4) endpoints
// serialize SQLite's naive datetimes without an offset; treat those as UTC rather
// than letting the browser misread them as local time.
const HAS_OFFSET = /(?:[zZ]|[+-]\d{2}:?\d{2})$/

export const formatDateTime = (value: string | null): string => {
  if (!value) return ''
  const date = new Date(HAS_OFFSET.test(value) ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
}

const pad = (value: number) => String(value).padStart(2, '0')

// <input type="datetime-local"> works in the browser's local time without an offset.
// Converting through Date makes the browser's own timezone explicit, and the API
// receives an ISO instant with a "Z" offset — never a naive timestamp.
export const toDatetimeLocal = (iso: string | null): string => {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export const fromDatetimeLocal = (value: string): string | null => {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

export const relativeDays = (days: number): string => {
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days === -1) return 'yesterday'
  return days > 0 ? `in ${days} days` : `${Math.abs(days)} days ago`
}

export const errorMessage = (error: unknown, fallback: string): string => error instanceof Error && error.message ? error.message : fallback
