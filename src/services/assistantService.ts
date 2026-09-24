import { API_BASE_URL } from '../config/api'

export type Intent =
  | 'JOB_DISCOVERY' | 'JOB_MATCH_EXPLANATION' | 'SKILL_GAP' | 'RESUME_CUSTOMIZATION'
  | 'COVER_LETTER' | 'INTERVIEW_PREP' | 'LEARNING_GUIDANCE' | 'JOB_COMPARISON'
  | 'PROFILE_SUMMARY' | 'NEXT_BEST_ACTION' | 'GENERAL_CAREER_CHAT'

export type MessageRole = 'user' | 'assistant'
export type ActionType =
  | 'upload_resume' | 'process_resume' | 'view_resume' | 'view_recommendations' | 'view_job'
  | 'analyze_skill_gap' | 'customize_application' | 'prepare_interview' | 'compare_jobs' | 'view_learning_plan'
export type GenerationMode = 'llm' | 'deterministic_fallback'

export type SuggestedAction = { label: string; action: ActionType; job_id: string | null }
export type GenerationMetadata = {
  mode: GenerationMode
  attempted_llm: boolean
  provider: string | null
  model: string | null
  repair_attempted: boolean
  fallback_reason: string | null
}
export type MessageOut = {
  id: number
  role: MessageRole
  content: string
  intent: Intent | null
  job_id: string | null
  resume_id: number | null
  suggested_actions: SuggestedAction[]
  context_used: string[]
  generation: GenerationMetadata | null
  created_at: string
}
export type ConversationSummary = {
  id: number
  title: string | null
  active_job_id: string | null
  active_resume_id: number | null
  message_count: number
  created_at: string
  updated_at: string
}
export type ConversationDetail = {
  id: number
  title: string | null
  active_job_id: string | null
  active_resume_id: number | null
  messages: MessageOut[]
  created_at: string
  updated_at: string
}
export type AssistantResponse = {
  message: MessageOut
  active_job_id: string | null
  active_resume_id: number | null
}

export class AssistantApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'AssistantApiError'
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
    throw new AssistantApiError(0, "We couldn't connect to the career assistant service. Please try again.")
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? String((body as { detail: unknown }).detail) : 'We could not complete that request.'
    throw new AssistantApiError(response.status, detail)
  }
  return body as T
}

export const createConversation = (title?: string, jobId?: string) =>
  request<ConversationDetail>('/api/career-assistant/conversations', { method: 'POST', body: JSON.stringify({ title: title ?? null, job_id: jobId ?? null }) })

export const listConversations = () => request<ConversationSummary[]>('/api/career-assistant/conversations')

export const getConversation = async (conversationId: number): Promise<ConversationDetail | null> => {
  try {
    return await request<ConversationDetail>(`/api/career-assistant/conversations/${conversationId}`)
  } catch (error: unknown) {
    if (error instanceof AssistantApiError && error.status === 404) return null
    throw error
  }
}

export const sendMessage = (conversationId: number, content: string, jobId?: string) =>
  request<AssistantResponse>(`/api/career-assistant/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, job_id: jobId ?? null }),
  })

export const deleteConversation = (conversationId: number) =>
  request<void>(`/api/career-assistant/conversations/${conversationId}`, { method: 'DELETE' })
