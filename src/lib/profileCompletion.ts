import type { CandidateProfilePayload } from '../services/profileService'

// The profile details a candidate fills in themselves. Full name and e-mail are left
// out on purpose: registration requires both, so counting them made every profile
// look partly complete (20%) before anything had been added.
export const PROFILE_COMPLETION_FIELDS = [
  'education', 'degree', 'specialization', 'experience_level',
  'career_interests', 'target_roles', 'skills', 'career_goals',
] as const satisfies ReadonlyArray<keyof CandidateProfilePayload>

type CompletionSource = Pick<CandidateProfilePayload, (typeof PROFILE_COMPLETION_FIELDS)[number]>

const isFilled = (value: string | string[] | null): boolean =>
  Array.isArray(value) ? value.some((item) => item.trim() !== '') : value !== null && value.trim() !== ''

export function profileCompletion(profile: CompletionSource): { filled: number; total: number; percent: number } {
  const filled = PROFILE_COMPLETION_FIELDS.filter((field) => isFilled(profile[field])).length
  const total = PROFILE_COMPLETION_FIELDS.length
  return { filled, total, percent: Math.round((filled / total) * 100) }
}
