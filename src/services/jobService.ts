import { API_BASE_URL } from '../config/api'

export type JobSearchResult = {
  job_id: string
  job_title: string
  company: string
  domain: string
  location: string
  work_mode: string
  employment_type: string
  required_skills: string[]
  preferred_skills: string[]
  similarity_score: number
  matched_chunk_types: string[]
  matched_text_preview: string | null
}

export type JobPosting = {
  job_id: string
  job_title: string
  company: string
  location: string
  work_mode: string
  employment_type: string
  domain: string
  job_description: string
  responsibilities: string[]
  required_skills: string[]
  preferred_skills: string[]
  qualifications: string[]
  experience_requirements: string
  education_requirements: string
  posted_date: string
}

export class JobApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'JobApiError'
    this.status = status
  }
}

const request = async <T>(path: string): Promise<T> => {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include' })
  } catch {
    throw new JobApiError(0, "We couldn't connect to the job search service. Please try again.")
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? String((body as { detail: unknown }).detail) : 'We could not complete that request.'
    throw new JobApiError(response.status, detail)
  }
  return body as T
}

export const searchJobs = (query: string, topK = 10) =>
  request<JobSearchResult[]>(`/api/jobs/search?q=${encodeURIComponent(query)}&top_k=${topK}`)

export const getJobDetails = (jobId: string) => request<JobPosting>(`/api/jobs/${encodeURIComponent(jobId)}`)
