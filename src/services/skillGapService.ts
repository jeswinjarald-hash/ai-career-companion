import { API_BASE_URL } from '../config/api'

export type EvidenceItem = { source: string; source_name: string; evidence: string }
export type MatchType = 'demonstrated' | 'partial' | 'missing'
export type RequirementType = 'required_skill' | 'preferred_skill' | 'qualification' | 'education' | 'experience'
export type Priority = 'high' | 'medium' | 'low'

export type StrengthItem = { requirement: string; requirement_type: RequirementType; evidence: EvidenceItem[]; reason: string }
export type GapItem = {
  requirement: string
  requirement_type: RequirementType
  match_type: MatchType
  priority: Priority
  confidence: number
  importance: string
  student_evidence: EvidenceItem[]
  reason: string
  recommendation: string
  suggested_evidence_to_build: string
}
export type ScoreComponent = { component: string; label: string; weight: number; included: boolean; score: number | null; matched: number; total: number }
export type SkillGapSummary = {
  overall_readiness: number
  required_requirements_met: number
  required_requirements_total: number
  preferred_requirements_met: number
  preferred_requirements_total: number
  critical_gap_count: number
  partial_gap_count: number
  preferred_gap_count: number
  experience_gap_count: number
  qualification_gap_count: number
  score_breakdown: ScoreComponent[]
}
export type SkillGapAnalysis = {
  job_id: string
  job_title: string
  company: string
  domain: string
  location: string
  resume_id: number
  profile_id: number
  generated_at: string
  resume_updated_at: string
  stale: boolean
  summary: SkillGapSummary
  strengths: StrengthItem[]
  critical_gaps: GapItem[]
  partial_gaps: GapItem[]
  preferred_gaps: GapItem[]
  experience_gaps: GapItem[]
  qualification_gaps: GapItem[]
  recommendations: GapItem[]
}

export class SkillGapApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'SkillGapApiError'
    this.status = status
  }
}

const request = async <T>(path: string, options?: RequestInit): Promise<T> => {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, credentials: 'include' })
  } catch {
    throw new SkillGapApiError(0, "We couldn't connect to the skill gap service. Please try again.")
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? String((body as { detail: unknown }).detail) : 'We could not complete that request.'
    throw new SkillGapApiError(response.status, detail)
  }
  return body as T
}

export const analyzeSkillGap = (resumeId: number, jobId: string) =>
  request<SkillGapAnalysis>(`/api/resumes/${resumeId}/skill-gap?job_id=${encodeURIComponent(jobId)}`, { method: 'POST' })

export const getSkillGap = async (resumeId: number, jobId: string): Promise<SkillGapAnalysis | null> => {
  try {
    return await request<SkillGapAnalysis>(`/api/resumes/${resumeId}/skill-gap/${encodeURIComponent(jobId)}`)
  } catch (error: unknown) {
    if (error instanceof SkillGapApiError && error.status === 404) return null
    throw error
  }
}
