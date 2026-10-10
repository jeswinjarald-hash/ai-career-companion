import { apiDetailMessage, apiFetch, fetchWithTimeout, GENERATION_TIMEOUT_MS, RequestTimeoutError } from '../config/api'

export type QuestionCategory = 'technical' | 'resume' | 'project' | 'role' | 'hr' | 'skill_gap'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type RevisionPriority = 'high' | 'medium' | 'low'
export type InterviewPrepStatus = 'ready' | 'validation_warning'
export type GenerationMode = 'llm' | 'deterministic_fallback'

export type InterviewQuestion = {
  question: string
  category: QuestionCategory
  difficulty: Difficulty
  why_asked: string
  what_interviewer_is_testing: string
  preparation_guidance: string
  topics_to_review: string[]
  source_requirements: string[]
  source_evidence_ids: string[]
}
export type RevisionItem = {
  priority: RevisionPriority
  topic: string
  reason: string
  suggested_revision: string
  estimated_focus: string
}
export type ConfidenceType = 'direct' | 'supporting' | 'learning_only'
export type SourceType = 'skill' | 'project' | 'experience' | 'internship' | 'education' | 'certification' | 'achievement' | 'qualification' | 'profile'
export type EvidenceRecord = {
  evidence_id: string
  source_type: SourceType
  source_name: string
  source_path: string
  raw_text: string
  canonical_terms: string[]
  confidence_type: ConfidenceType
}
export type ValidationResult = { passed: boolean; warnings: string[]; removed_claims: string[] }
export type GenerationMetadata = {
  mode: GenerationMode
  attempted_llm: boolean
  provider: string | null
  model: string | null
  repair_attempted: boolean
  fallback_reason: string | null
}
export type InterviewPreparation = {
  id: number
  resume_id: number
  job_id: string
  job_title: string
  company: string
  version: number
  status: InterviewPrepStatus
  stale: boolean
  parser_warning_notice: string | null
  preparation_summary: string
  questions: InterviewQuestion[]
  revision_plan: RevisionItem[]
  evidence: EvidenceRecord[]
  validation: ValidationResult
  generation: GenerationMetadata
  created_at: string
  updated_at: string
}
export type InterviewPreparationSummary = {
  id: number
  resume_id: number
  job_id: string
  job_title: string
  company: string
  version: number
  status: InterviewPrepStatus
  stale: boolean
  generation_mode: GenerationMode
  created_at: string
  updated_at: string
}
export type MockAnswerEvaluation = {
  strengths: string[]
  improvements: string[]
  missing_points: string[]
  suggested_structure: string
  grounded_feedback: string
  generation: GenerationMetadata
}

export class InterviewPrepApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'InterviewPrepApiError'
    this.status = status
  }
}

const request = async <T>(path: string, options?: RequestInit, timeoutMs?: number): Promise<T> => {
  let response: Response
  try {
    const init = { ...options, headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) } }
    response = timeoutMs ? await fetchWithTimeout(path, init, timeoutMs) : await apiFetch(path, init)
  } catch (error: unknown) {
    if (error instanceof RequestTimeoutError) {
      throw new InterviewPrepApiError(0, "Generating interview preparation is taking longer than expected, so we stopped waiting. The server may still finish it — check the version list before trying again.")
    }
    throw new InterviewPrepApiError(0, "We couldn't connect to the interview preparation service. Please try again.")
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new InterviewPrepApiError(response.status, apiDetailMessage(body, 'We could not complete that request.', response.status))
  }
  return body as T
}

export const generateInterviewPreparation = (resumeId: number, jobId: string) =>
  request<InterviewPreparation>(`/api/resumes/${resumeId}/interview-preparations?job_id=${encodeURIComponent(jobId)}`, { method: 'POST' }, GENERATION_TIMEOUT_MS)

export const listInterviewPreparations = (resumeId: number, jobId?: string) =>
  request<InterviewPreparationSummary[]>(`/api/resumes/${resumeId}/interview-preparations${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''}`)

export const getInterviewPreparation = async (resumeId: number, prepId: number): Promise<InterviewPreparation | null> => {
  try {
    return await request<InterviewPreparation>(`/api/resumes/${resumeId}/interview-preparations/${prepId}`)
  } catch (error: unknown) {
    if (error instanceof InterviewPrepApiError && error.status === 404) return null
    throw error
  }
}

export const regenerateInterviewPreparation = (resumeId: number, prepId: number) =>
  request<InterviewPreparation>(`/api/resumes/${resumeId}/interview-preparations/${prepId}/regenerate`, { method: 'POST' }, GENERATION_TIMEOUT_MS)

export const submitMockAnswer = (resumeId: number, prepId: number, questionIndex: number, answer: string) =>
  request<MockAnswerEvaluation>(`/api/resumes/${resumeId}/interview-preparations/${prepId}/mock-answer`, {
    method: 'POST',
    body: JSON.stringify({ question_index: questionIndex, answer }),
  })
