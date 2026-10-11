// Pure, documented derivations from real API data, used by the dashboard and charts.
// Nothing here invents values: every output is a count, a ratio or a classification of
// fields the backend returned. Unit-tested in tests/unit/insights.test.ts.
import type { ApplicationStatus } from '../services/applicationService'
import type { ResumeRecord, StructuredResume } from '../services/resumeService'
import type { ScoreComponent } from '../services/skillGapService'

// ---------------------------------------------------------------- dashboard state
export type ResumeLifecycle = 'no_resume' | 'awaiting_analysis' | 'uploading' | 'processing' | 'processed' | 'failed'
export type DashboardStateKind = 'loading' | 'load_error' | 'no_resume' | 'awaiting_analysis' | 'processing' | 'failed' | 'stale' | 'ready'

// The parser stamps resumes processed by an older parser version with this warning
// (backend/app/services/structured_resume.py); results are then outdated until reprocessed.
export const OUTDATED_PARSER_WARNING = 'outdated_parser_version'

// loadError: the resume status itself could not be loaded (e.g. network failure) — this
// is not an analysis failure and must not be presented as one.
export function dashboardState(input: { restoring: boolean; loadError?: string; lifecycle: ResumeLifecycle; structured: StructuredResume | null }): DashboardStateKind {
  if (input.restoring) return 'loading'
  if (input.loadError) return 'load_error'
  switch (input.lifecycle) {
    case 'no_resume': return 'no_resume'
    case 'awaiting_analysis': return 'awaiting_analysis'
    case 'uploading':
    case 'processing': return 'processing'
    case 'failed': return 'failed'
    case 'processed':
      if (!input.structured) return 'awaiting_analysis'
      return (input.structured.data.parser_warnings ?? []).some((warning) => warning.startsWith(OUTDATED_PARSER_WARNING)) ? 'stale' : 'ready'
  }
}

// A stored resume without a structured result: was the last attempt a failure, or did
// processing simply never finish (e.g. the page was closed mid-way)? Mirrors the
// backend statuses uploaded → extracting_text → text_extracted | extraction_failed.
export const lifecycleForUnstructured = (record: ResumeRecord): ResumeLifecycle =>
  record.status === 'extraction_failed' ? 'failed' : 'awaiting_analysis'

// ---------------------------------------------------------------- match score
// Mirrors MATCH_WEIGHTS in backend/app/services/job_matching.py.
export const MATCH_SCORE_DEFINITION = 'Match score: the weighted share of an opportunity’s requirements your resume and profile meet — required skills 35%, preferred skills 15%, experience 15%, project relevance 15%, education 10%, qualifications 10%. Requirements that cannot be assessed are left out of the weighting.'

// ---------------------------------------------------------------- resume coverage
export type CoverageRow = { key: string; label: string; count: number; found: boolean }

// Which standard resume sections the parser extracted at least one entry from.
// "found" means ≥ 1 extracted entry (summary: non-empty text). It describes what was
// extracted from the file, not the quality of the resume.
export function resumeCoverage(data: StructuredResume['data']): CoverageRow[] {
  const rows: Array<[string, string, number]> = [
    ['summary', 'Summary', data.summary && data.summary.trim() ? 1 : 0],
    ['skills', 'Skills', data.skills.length],
    ['education', 'Education', data.education.length],
    ['experience', 'Experience & internships', data.experience.length + data.internships.length],
    ['projects', 'Projects', data.projects.length],
    ['certifications', 'Certifications', data.certifications.length],
    ['achievements', 'Achievements', data.achievements.length],
  ]
  return rows.map(([key, label, count]) => ({ key, label, count, found: count > 0 }))
}

// ---------------------------------------------------------------- skill-gap readiness
export type ReadinessRow = { key: string; label: string; percent: number | null; weightPercent: number; detail: string; included: boolean }

// One row per backend score component (skill_gap_service.py): the component score as a
// percentage (score × 100), its nominal weight, and matched/total. A component the
// backend did not assess (included = false) has no score and is shown as such.
export function readinessRows(breakdown: ScoreComponent[]): ReadinessRow[] {
  return breakdown.map((component) => {
    const assessed = component.included && component.score !== null
    return {
      key: component.component,
      label: component.label,
      percent: assessed ? Math.round((component.score as number) * 100) : null,
      weightPercent: Math.round(component.weight * 100),
      detail: !assessed ? 'Not assessed' : component.total > 0 ? `${component.matched} of ${component.total} met` : 'Assessed',
      included: assessed,
    }
  })
}

// Recomputes overall readiness exactly as the backend does: the weighted mean of the
// assessed components, re-normalised over their weights. Used to verify that what the
// chart shows is consistent with the headline number.
export function readinessFromBreakdown(breakdown: ScoreComponent[]): number {
  const assessed = breakdown.filter((component) => component.included && component.score !== null)
  const totalWeight = assessed.reduce((sum, component) => sum + component.weight, 0)
  if (totalWeight === 0) return 0
  return Math.round((assessed.reduce((sum, component) => sum + (component.score as number) * component.weight, 0) / totalWeight) * 100)
}

// ---------------------------------------------------------------- application pipeline
export const PIPELINE_ORDER: ApplicationStatus[] = ['saved', 'planning', 'applied', 'under_review', 'shortlisted', 'interview_scheduled', 'interview_completed', 'offer', 'rejected', 'withdrawn']
export type StatusRow = { status: ApplicationStatus; count: number }

// Non-zero application counts per status, in pipeline order (GET /api/applications/summary
// → status_counts). Statuses with no applications are omitted rather than drawn as zeros.
export function applicationStatusRows(counts: Partial<Record<ApplicationStatus, number>> | null | undefined): StatusRow[] {
  if (!counts) return []
  return PIPELINE_ORDER.map((status) => ({ status, count: Math.max(0, Math.trunc(counts[status] ?? 0)) })).filter((row) => row.count > 0)
}
