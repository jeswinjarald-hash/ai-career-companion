// Skill labels for the decorative skill graph — real data only.
// Sources (both already loaded by App, no extra request): the active resume's extracted
// skills (StructuredResume.data.skills, the latest analysed resume — the same selection rule
// as the rest of the app) followed by the career profile's own skills list. Nothing is ever
// substituted when these are empty. Unit-tested in tests/unit/skillGraph.test.ts.

// Longer values are almost certainly parsing fragments rather than skill names.
export const MAX_SKILL_LABEL_LENGTH = 32
export const MAX_SKILL_LABEL_WORDS = 4

// Accepts only plain strings that look like a skill name: trimmed, whitespace collapsed,
// 1–32 characters, at most 4 words, no control characters or markup-like brackets.
export function normalizeSkillLabel(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const label = value.replace(/\s+/g, ' ').trim()
  if (label.length === 0 || label.length > MAX_SKILL_LABEL_LENGTH) return null
  if (label.split(' ').length > MAX_SKILL_LABEL_WORDS) return null
  for (const char of label) {
    const code = char.codePointAt(0) ?? 0
    if (code < 0x20 || code === 0x7f || '<>{}'.includes(char)) return null   // control characters, markup-like brackets
  }
  if (!/[\p{L}\p{N}]/u.test(label)) return null
  return label
}

// Normalises and de-duplicates (case-insensitively, first spelling wins) in source order.
export function normalizeSkills(values: readonly unknown[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    const label = normalizeSkillLabel(value)
    if (!label) continue
    const key = label.toLocaleLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(label)
  }
  return result
}

// Skills for the graph from the two real sources. Resume skills count only once the
// resume has been analysed; profile skills are what the user entered themselves.
export function graphSkills(input: { resumeSkills?: readonly unknown[] | null; profileSkills?: readonly unknown[] | null }): string[] {
  return normalizeSkills([...(input.resumeSkills ?? []), ...(input.profileSkills ?? [])])
}

// Deterministic visible subset: the first `cap` labels in source order (resume order is the
// order the parser found them). A rendering limit only — stored skills are untouched.
export function selectVisibleSkills(skills: readonly string[], cap: number): string[] {
  return skills.slice(0, Math.max(0, Math.floor(cap)))
}

// Real skill gaps from an existing skill-gap analysis response: skill requirements (required
// or preferred) whose match type is anything other than 'demonstrated'. Qualifications,
// education and experience requirements are not skills and are left out; long requirement
// sentences fail normalisation. Nothing is inferred from what a resume lacks.
type GapLike = { requirement: unknown; requirement_type: string; match_type: string }
export function gapSkillsFromAnalysis(analysis: { critical_gaps: readonly GapLike[]; partial_gaps: readonly GapLike[]; preferred_gaps: readonly GapLike[] } | null | undefined): string[] {
  if (!analysis) return []
  const items = [...analysis.critical_gaps, ...analysis.partial_gaps, ...analysis.preferred_gaps]
  return normalizeSkills(items.filter((item) => (item.requirement_type === 'required_skill' || item.requirement_type === 'preferred_skill') && item.match_type !== 'demonstrated').map((item) => item.requirement))
}

export type SceneLabel = { label: string; gap: boolean }
// The labels drawn for a scene, within the node cap. Without gap data this is exactly
// selectVisibleSkills(skills, cap). With gap data, a user skill that is a reported gap is
// marked, and gap requirements not among the user's skills are added (up to a third of the
// cap, so the user's own skills stay the majority).
export function sceneLabels(skills: readonly string[], gapSkills: readonly string[], cap: number): SceneLabel[] {
  const limit = Math.max(0, Math.floor(cap))
  const gaps = normalizeSkills(gapSkills)
  if (gaps.length === 0) return selectVisibleSkills(skills, limit).map((label) => ({ label, gap: false }))
  const gapKeys = new Set(gaps.map((label) => label.toLocaleLowerCase()))
  const own = new Set(skills.map((label) => label.toLocaleLowerCase()))
  const extra = gaps.filter((label) => !own.has(label.toLocaleLowerCase())).slice(0, Math.floor(limit / 3))
  const mine = selectVisibleSkills(skills, limit - extra.length).map((label) => ({ label, gap: gapKeys.has(label.toLocaleLowerCase()) }))
  return [...mine, ...extra.map((label) => ({ label, gap: true }))]
}
