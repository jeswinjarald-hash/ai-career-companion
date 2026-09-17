import { API_BASE_URL } from '../config/api'

export type ResumeRecord = { id: number; candidate_profile_id: number; original_filename: string; file_type: string; mime_type: string | null; file_size: number; status: string; created_at: string; updated_at: string }
export type ResumeExtraction = { id: number; resume_id: number; status: string; page_count: number | null; character_count: number; raw_text: string | null; normalized_text: string | null; error_message: string | null; created_at: string; updated_at: string }
export type StructuredResume = { id: number; resume_id: number; data: { skills: string[]; education: Array<Record<string, unknown>>; experience: Array<Record<string, unknown>>; internships: Array<Record<string, unknown>>; projects: Array<Record<string, unknown>>; certifications: Array<Record<string, unknown>>; achievements: Array<Record<string, unknown>>; qualifications: Array<Record<string, unknown>>; header: string; summary: string | null } }
export type JobMatchResult = { job_id: string; job_title: string; company: string; domain: string; location: string; work_mode: string; employment_type: string; retrieval_score: number; match_score: number; required_skills_score: number; preferred_skills_score: number; experience_score: number; education_score: number; project_relevance_score: number; qualification_score: number; matched_required_skills: string[]; missing_required_skills: string[]; matched_preferred_skills: string[]; missing_preferred_skills: string[]; relevant_projects: string[]; strengths: string[]; gaps: string[]; reasoning: string }
export type CandidateContext = { id: number; candidate_profile_id: number; resume_id: number; context_json: Record<string, unknown> }

export class ResumeApiError extends Error { status: number; constructor(status: number, message: string) { super(message); this.status = status; this.name = 'ResumeApiError' } }

const request = async <T>(path: string, options?: RequestInit): Promise<T> => {
  let response: Response
  try { response = await fetch(`${API_BASE_URL}${path}`, { ...options, credentials: 'include' }) } catch { throw new ResumeApiError(0, "We couldn't connect to the resume service. Please try again.") }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? String((body as { detail: unknown }).detail) : 'We could not process this resume.'
    throw new ResumeApiError(response.status, detail)
  }
  return body as T
}

export const uploadResume = (profileId: number, file: File) => { const form = new FormData(); form.append('file', file); return request<ResumeRecord>(`/api/profiles/${profileId}/resumes`, { method: 'POST', body: form }) }
export const extractResumeText = (resumeId: number) => request(`/api/resumes/${resumeId}/extract-text`, { method: 'POST' })
export const detectResumeSections = (resumeId: number) => request(`/api/resumes/${resumeId}/detect-sections`, { method: 'POST' })
export const structureResume = (resumeId: number) => request<StructuredResume>(`/api/resumes/${resumeId}/structure`, { method: 'POST' })
export const createCandidateContext = (profileId: number, resumeId: number) => request<CandidateContext>(`/api/profiles/${profileId}/candidate-context?resume_id=${resumeId}`, { method: 'POST' })
export const getResume = (resumeId: number) => request<ResumeRecord>(`/api/resumes/${resumeId}`)
export const getResumeExtraction = (resumeId: number) => request<ResumeExtraction>(`/api/resumes/${resumeId}/extraction`)
// The authoritative "active resume" for a profile — always the most recently uploaded one, per the backend's ordering. Never sourced from browser storage.
export const listProfileResumes = (profileId: number) => request<ResumeRecord[]>(`/api/profiles/${profileId}/resumes`)
export const getStructuredResume = async (resumeId: number): Promise<StructuredResume | null> => {
  try { return await request<StructuredResume>(`/api/resumes/${resumeId}/structured`) } catch (error: unknown) {
    if (error instanceof ResumeApiError && error.status === 404) return null
    throw error
  }
}
export const getJobMatches = (resumeId: number, topK = 5) => request<JobMatchResult[]>(`/api/resumes/${resumeId}/job-matches?top_k=${topK}`)
