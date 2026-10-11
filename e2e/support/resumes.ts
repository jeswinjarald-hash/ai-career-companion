import { readFileSync } from 'node:fs'
import path from 'node:path'
import { expect, type Locator, type Page } from '@playwright/test'
import { API_URL } from './fixtures'

// Synthetic, fictional resumes written by e2e/support/make_synthetic_resume.py when the
// isolated backend starts. Nothing here ever reads backend/data/resumes.
export const SYNTHETIC_RESUMES = {
  backend: path.resolve('e2e/.tmp/backend-data/fixtures/synthetic-resume.docx'),
  marketing: path.resolve('e2e/.tmp/backend-data/fixtures/synthetic-resume-marketing.docx'),
} as const

export type Match = { job_id: string; job_title: string; company: string; match_score: number; missing_required_skills: string[] }

// Uploads a synthetic resume and runs the same five pipeline calls the Resume Analyzer
// makes, asserting each one succeeds. Returns the new resume id.
export async function processResumeViaApi(page: Page, profileId: number, resume: keyof typeof SYNTHETIC_RESUMES = 'backend'): Promise<number> {
  const uploaded = await page.request.post(`${API_URL}/api/profiles/${profileId}/resumes`, {
    multipart: { file: { name: path.basename(SYNTHETIC_RESUMES[resume]), mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: readFileSync(SYNTHETIC_RESUMES[resume]) } },
  })
  expect(uploaded.status(), 'synthetic resume upload').toBe(201)
  const resumeId = (await uploaded.json() as { id: number }).id
  for (const step of ['extract-text', 'detect-sections', 'structure']) {
    expect((await page.request.post(`${API_URL}/api/resumes/${resumeId}/${step}`)).status(), step).toBe(200)
  }
  expect((await page.request.post(`${API_URL}/api/profiles/${profileId}/candidate-context?resume_id=${resumeId}`)).status(), 'candidate context').toBe(200)
  return resumeId
}

export const jobMatches = async (page: Page, resumeId: number, topK: number): Promise<Match[]> => {
  const response = await page.request.get(`${API_URL}/api/resumes/${resumeId}/job-matches?top_k=${topK}`)
  expect(response.status(), 'job matches').toBe(200)
  return await response.json() as Match[]
}

// Holds every matching request until release() — lets a test decide exactly when a
// slow response arrives. Requests are continued to the real backend, never faked.
export async function holdRequests(page: Page, pattern: string) {
  const held: Array<() => Promise<void>> = []
  let released = false
  await page.route(pattern, async (route) => {
    if (released) return route.continue()
    await new Promise<void>((resolve) => held.push(async () => { await route.continue(); resolve() }))
  })
  return {
    count: () => held.length,
    release: async () => { released = true; await Promise.all(held.splice(0).map((go) => go())) },
  }
}

// Asserts a locator stays absent for a window of time (not just at one instant), so a
// late state update — e.g. a stale response applied after the fact — is caught.
export async function staysAbsent(locator: Locator, milliseconds = 1500) {
  const deadline = Date.now() + milliseconds
  while (Date.now() < deadline) {
    expect(await locator.count()).toBe(0)
    await locator.page().waitForTimeout(100)
  }
}
