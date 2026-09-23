import { API_BASE_URL } from '../config/api'

export type ConfidenceType = 'direct' | 'supporting' | 'learning_only'
export type SourceType = 'skill' | 'project' | 'experience' | 'internship' | 'education' | 'certification' | 'achievement' | 'qualification' | 'profile'
export type KeywordStatus = 'supported' | 'partial' | 'unsupported'
export type KeywordRequirementType = 'required_skill' | 'preferred_skill'
export type CustomizationStatus = 'ready' | 'validation_warning'
export type GenerationMode = 'llm' | 'deterministic_fallback'

export type EvidenceRecord = {
  evidence_id: string
  source_type: SourceType
  source_name: string
  source_path: string
  raw_text: string
  canonical_terms: string[]
  confidence_type: ConfidenceType
}
export type KeywordClassification = {
  keyword: string
  requirement_type: KeywordRequirementType
  status: KeywordStatus
  reason: string
  matched_evidence_ids: string[]
}
export type TailoredBullet = { original_text: string; tailored_text: string; source_path: string; job_keywords_used: string[]; evidence_ids: string[]; introduced_claims: string[] }
export type TailoredProject = {
  title: string
  original_text: string
  tailored_text: string
  technologies: string[]
  source_path: string
  relevance_rank: number
  job_keywords_used: string[]
  evidence_ids: string[]
  introduced_claims: string[]
}
export type TailoredEducationEntry = { raw_text: string; source_path: string }
export type TailoredResume = {
  header: string
  summary: string
  summary_sources: string[]
  skills: string[]
  education: TailoredEducationEntry[]
  projects: TailoredProject[]
  experience: TailoredBullet[]
  internships: TailoredBullet[]
  certifications: string[]
  achievements: string[]
}
export type CoverLetterSentence = { text: string; sources: string[]; evidence_ids: string[] }
export type ValidationResult = { passed: boolean; warnings: string[]; removed_claims: string[] }
export type GenerationMetadata = {
  mode: GenerationMode
  attempted_llm: boolean
  provider: string | null
  model: string | null
  repair_attempted: boolean
  fallback_reason: string | null
}
export type UserEdits = { summary: string | null; cover_letter_text: string | null; bullet_edits: Record<string, string>; edited_fields: string[] }
export type ApplicationCustomization = {
  id: number
  resume_id: number
  job_id: string
  job_title: string
  company: string
  version: number
  status: CustomizationStatus
  stale: boolean
  parser_warning_notice: string | null
  evidence: EvidenceRecord[]
  keyword_classification: KeywordClassification[]
  tailored_resume: TailoredResume
  cover_letter: CoverLetterSentence[]
  cover_letter_text: string
  validation: ValidationResult
  generation: GenerationMetadata
  user_edits: UserEdits
  created_at: string
  updated_at: string
}
export type ApplicationCustomizationSummary = {
  id: number
  resume_id: number
  job_id: string
  job_title: string
  company: string
  version: number
  status: CustomizationStatus
  stale: boolean
  generation_mode: GenerationMode
  created_at: string
  updated_at: string
}
export type ApplicationCustomizationEditPayload = { summary?: string; cover_letter_text?: string; bullet_edits?: Record<string, string> }

export class CustomizationApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'CustomizationApiError'
    this.status = status
  }
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
    throw new CustomizationApiError(0, "We couldn't connect to the application customization service. Please try again.")
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? String((body as { detail: unknown }).detail) : 'We could not complete that request.'
    throw new CustomizationApiError(response.status, detail)
  }
  return body as T
}

export const generateCustomization = (resumeId: number, jobId: string) =>
  request<ApplicationCustomization>(`/api/resumes/${resumeId}/application-customizations?job_id=${encodeURIComponent(jobId)}`, { method: 'POST' })

export const listCustomizations = (resumeId: number, jobId?: string) =>
  request<ApplicationCustomizationSummary[]>(`/api/resumes/${resumeId}/application-customizations${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ''}`)

export const getCustomization = async (resumeId: number, customizationId: number): Promise<ApplicationCustomization | null> => {
  try {
    return await request<ApplicationCustomization>(`/api/resumes/${resumeId}/application-customizations/${customizationId}`)
  } catch (error: unknown) {
    if (error instanceof CustomizationApiError && error.status === 404) return null
    throw error
  }
}

export const updateCustomization = (resumeId: number, customizationId: number, payload: ApplicationCustomizationEditPayload) =>
  request<ApplicationCustomization>(`/api/resumes/${resumeId}/application-customizations/${customizationId}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const regenerateCustomization = (resumeId: number, customizationId: number) =>
  request<ApplicationCustomization>(`/api/resumes/${resumeId}/application-customizations/${customizationId}/regenerate`, { method: 'POST' })

export type ExportDocument = 'resume' | 'cover_letter'
export type ExportFormat = 'pdf' | 'docx'

const exportUrl = (resumeId: number, customizationId: number, docType: ExportDocument, format: ExportFormat) =>
  `${API_BASE_URL}/api/resumes/${resumeId}/application-customizations/${customizationId}/export?document=${docType}&format=${format}`

// Fetches the export as a blob (carrying the session cookie) and triggers a browser
// download, rather than a plain <a href> to the API origin — this works regardless
// of the cookie's SameSite policy and surfaces a real error message on failure
// instead of silently navigating to a JSON error body.
export const downloadExport = async (resumeId: number, customizationId: number, docType: ExportDocument, format: ExportFormat): Promise<void> => {
  let response: Response
  try {
    response = await fetch(exportUrl(resumeId, customizationId, docType, format), { credentials: 'include' })
  } catch {
    throw new CustomizationApiError(0, "We couldn't connect to the export service. Please try again.")
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body && typeof body === 'object' && 'detail' in body ? String((body as { detail: unknown }).detail) : 'We could not generate this export.'
    throw new CustomizationApiError(response.status, detail)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') ?? ''
  const match = /filename="([^"]+)"/.exec(disposition)
  const filename = match ? match[1] : `${docType}.${format}`
  const blobUrl = window.URL.createObjectURL(blob)
  const link = window.document.createElement('a')
  link.href = blobUrl
  link.download = filename
  window.document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(blobUrl)
}
