import type { Page } from '@playwright/test'
import { expect, newAccount, registerViaApi, test } from './support/fixtures'
import { holdRequests, jobMatches, processResumeViaApi, staysAbsent, type Match } from './support/resumes'

// Defect E lifecycle: the real RoadmapView, mounted by the test harness
// (e2e/harness/roadmap.html), with real data from two synthetic resumes in different
// domains. The harness changes `resumeId` while the view stays mounted; request timing
// is controlled by holding real requests, never by faking their responses.
const contextHeading = (page: Page, match: Match) =>
  page.getByRole('heading', { level: 3, name: `From your top job match: ${match.job_title}, ${match.company}` })
const setResumeId = (page: Page, id: number | null) => page.evaluate((value) => window.roadmapHarness!.setResumeId(value), id)

async function twoResumes(page: Page) {
  const profileId = await registerViaApi(page, newAccount('roadmap'))
  const first = await processResumeViaApi(page, profileId, 'backend')
  const second = await processResumeViaApi(page, profileId, 'marketing')
  const firstTop = (await jobMatches(page, first, 1))[0]
  const secondTop = (await jobMatches(page, second, 1))[0]
  expect(firstTop.job_id, 'the two synthetic resumes must have different top matches').not.toBe(secondTop.job_id)
  expect(secondTop.missing_required_skills.length, 'precondition: the second resume has visible gap chips').toBeGreaterThan(0)
  await page.goto('/e2e/harness/roadmap.html')
  await expect.poll(() => page.evaluate(() => Boolean(window.roadmapHarness))).toBe(true)
  return { first, second, firstTop, secondTop }
}

test('changing the resume clears the previous context before the new one loads', async ({ page }) => {
  const { first, second, firstTop, secondTop } = await twoResumes(page)
  await setResumeId(page, first)
  await expect(contextHeading(page, firstTop)).toBeVisible()

  const slow = await holdRequests(page, `**/api/resumes/${second}/job-matches*`)
  await setResumeId(page, second)
  await expect(page.getByRole('status').filter({ hasText: 'Loading the skill gap context' })).toBeVisible()
  await expect(contextHeading(page, firstTop)).toHaveCount(0)        // reset, not left on screen
  await slow.release()
  await expect(contextHeading(page, secondTop)).toBeVisible()
  await expect(page.locator('.warning-chip')).toHaveText(secondTop.missing_required_skills)
})

test("a slow response for the previous resume never overwrites the current one", async ({ page }) => {
  const { first, second, firstTop, secondTop } = await twoResumes(page)
  const slow = await holdRequests(page, `**/api/resumes/${first}/job-matches*`)
  await setResumeId(page, first)
  await expect.poll(slow.count).toBeGreaterThan(0)                    // first resume's request in flight
  await setResumeId(page, second)
  await expect(contextHeading(page, secondTop)).toBeVisible()

  const lateResponse = page.waitForResponse((response) => response.url().includes(`/api/resumes/${first}/job-matches`))
  await slow.release()                                                // first resume's real response arrives last
  await lateResponse
  await staysAbsent(contextHeading(page, firstTop))
  await expect(contextHeading(page, secondTop)).toBeVisible()
  await expect(page.locator('.warning-chip')).toHaveText(secondTop.missing_required_skills)
})

test('clearing the resume clears the context', async ({ page }) => {
  const { first, firstTop } = await twoResumes(page)
  await setResumeId(page, first)
  await expect(contextHeading(page, firstTop)).toBeVisible()
  await setResumeId(page, null)
  await expect(page.getByText('CURRENT SKILL GAP CONTEXT')).toHaveCount(0)
})
