import { expect, test } from '@playwright/test'
import {
  applicationStatusRows, dashboardState, lifecycleForUnstructured, readinessFromBreakdown, readinessRows, resumeCoverage,
} from '../../src/lib/insights'
import type { ResumeRecord, StructuredResume } from '../../src/services/resumeService'
import type { ScoreComponent } from '../../src/services/skillGapService'

const emptyData: StructuredResume['data'] = {
  skills: [], education: [], experience: [], internships: [], projects: [], certifications: [], achievements: [], qualifications: [], header: '', summary: null,
}
const structured = (data: Partial<StructuredResume['data']> = {}): StructuredResume => ({ id: 1, resume_id: 1, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', data: { ...emptyData, ...data } })
const record = (status: string): ResumeRecord => ({ id: 1, candidate_profile_id: 1, original_filename: 'r.pdf', file_type: 'pdf', mime_type: null, file_size: 1, status, created_at: '', updated_at: '' })

test.describe('dashboard state', () => {
  test('maps every lifecycle to exactly one state', () => {
    expect(dashboardState({ restoring: true, lifecycle: 'processed', structured: structured() })).toBe('loading')
    expect(dashboardState({ restoring: false, loadError: 'network', lifecycle: 'no_resume', structured: null })).toBe('load_error')
    expect(dashboardState({ restoring: false, lifecycle: 'no_resume', structured: null })).toBe('no_resume')
    expect(dashboardState({ restoring: false, lifecycle: 'awaiting_analysis', structured: null })).toBe('awaiting_analysis')
    expect(dashboardState({ restoring: false, lifecycle: 'uploading', structured: null })).toBe('processing')
    expect(dashboardState({ restoring: false, lifecycle: 'processing', structured: null })).toBe('processing')
    expect(dashboardState({ restoring: false, lifecycle: 'failed', structured: null })).toBe('failed')
    expect(dashboardState({ restoring: false, lifecycle: 'processed', structured: structured() })).toBe('ready')
  })

  test('results from an earlier parser version are stale, never current', () => {
    const outdated = structured({ parser_warnings: ['outdated_parser_version: this resume was structured by an earlier parser version; reprocess it'] })
    expect(dashboardState({ restoring: false, lifecycle: 'processed', structured: outdated })).toBe('stale')
    const otherWarning = structured({ parser_warnings: ['project entry looks like a fragment'] })
    expect(dashboardState({ restoring: false, lifecycle: 'processed', structured: otherWarning })).toBe('ready')
  })

  test('a stored resume without results is a failure only when extraction failed', () => {
    expect(lifecycleForUnstructured(record('extraction_failed'))).toBe('failed')
    for (const status of ['uploaded', 'extracting_text', 'text_extracted']) expect(lifecycleForUnstructured(record(status))).toBe('awaiting_analysis')
  })
})

test.describe('resume coverage', () => {
  test('empty extraction finds no sections', () => {
    const rows = resumeCoverage(emptyData)
    expect(rows.map((row) => row.found)).toEqual(rows.map(() => false))
    expect(rows.every((row) => row.count === 0)).toBe(true)
  })

  test('counts come straight from the extracted lists', () => {
    const rows = resumeCoverage({ ...emptyData, summary: '  Backend student  ', skills: ['Python', 'SQL'], experience: [{}], internships: [{}, {}], projects: [{}] })
    const byKey = Object.fromEntries(rows.map((row) => [row.key, row]))
    expect(byKey.summary).toMatchObject({ count: 1, found: true })
    expect(byKey.skills).toMatchObject({ count: 2, found: true })
    expect(byKey.experience).toMatchObject({ count: 3, found: true })
    expect(byKey.projects).toMatchObject({ count: 1, found: true })
    expect(byKey.education).toMatchObject({ count: 0, found: false })
    expect(resumeCoverage({ ...emptyData, summary: '   ' }).find((row) => row.key === 'summary')?.found).toBe(false)
  })
})

test.describe('skill-gap readiness breakdown', () => {
  const component = (overrides: Partial<ScoreComponent>): ScoreComponent => ({ component: 'required_skills', label: 'Required skills', weight: 0.4, included: true, score: 1, matched: 1, total: 1, ...overrides })

  test('empty breakdown has no rows and zero readiness', () => {
    expect(readinessRows([])).toEqual([])
    expect(readinessFromBreakdown([])).toBe(0)
  })

  test('unassessed components are not shown as zero', () => {
    const rows = readinessRows([component({ component: 'education', label: 'Education', weight: 0.1, included: false, score: null, matched: 0, total: 0 })])
    expect(rows[0]).toMatchObject({ percent: null, included: false, detail: 'Not assessed', weightPercent: 10 })
  })

  test('partial data: readiness is re-normalised over assessed components, as the backend does', () => {
    const breakdown = [
      component({ component: 'required_skills', weight: 0.4, score: 0.5, matched: 2, total: 4 }),
      component({ component: 'preferred_skills', label: 'Preferred skills', weight: 0.15, score: 1, matched: 2, total: 2 }),
      component({ component: 'experience', label: 'Experience', weight: 0.2, score: 0, matched: 0, total: 1 }),
      component({ component: 'education', label: 'Education', weight: 0.1, included: false, score: null, matched: 0, total: 0 }),
      component({ component: 'qualifications', label: 'Qualifications', weight: 0.15, included: false, score: null, matched: 0, total: 0 }),
    ]
    // (0.5×0.4 + 1×0.15 + 0×0.2) / (0.4 + 0.15 + 0.2) = 0.35 / 0.75 = 46.7% → 47
    expect(readinessFromBreakdown(breakdown)).toBe(47)
    expect(readinessRows(breakdown).map((row) => [row.percent, row.detail])).toEqual([[50, '2 of 4 met'], [100, '2 of 2 met'], [0, '0 of 1 met'], [null, 'Not assessed'], [null, 'Not assessed']])
  })
})

test.describe('application status rows', () => {
  test('missing or empty counts produce no rows', () => {
    expect(applicationStatusRows(null)).toEqual([])
    expect(applicationStatusRows({})).toEqual([])
    expect(applicationStatusRows({ saved: 0, applied: 0 })).toEqual([])
  })

  test('only non-zero statuses, in pipeline order, with exact counts', () => {
    expect(applicationStatusRows({ rejected: 1, saved: 3, offer: 0, applied: 2 })).toEqual([{ status: 'saved', count: 3 }, { status: 'applied', count: 2 }, { status: 'rejected', count: 1 }])
  })

  test('invalid values never become negative or fractional bars', () => {
    expect(applicationStatusRows({ saved: -2, applied: 2.7 })).toEqual([{ status: 'applied', count: 2 }])
  })
})
