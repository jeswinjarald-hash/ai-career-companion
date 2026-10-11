import type { Page } from '@playwright/test'
import { API_URL, expect, newAccount, registerViaApi, test } from './support/fixtures'
import { holdRequests, jobMatches, processResumeViaApi, staysAbsent } from './support/resumes'

// Regression tests for defects B, C and E. Every expected value is read from the real
// isolated backend in the same test, so the UI is checked against actual API output.
// Failures are injected only in the browser (route.fulfill) to exercise error states.

async function accountWithProcessedResume(page: Page, resume: 'backend' | 'marketing' = 'backend'): Promise<number> {
  return processResumeViaApi(page, await registerViaApi(page, newAccount('resume')), resume)
}

const failJobMatches = (page: Page) => page.route('**/api/resumes/*/job-matches*', (route) =>
  route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'A structured resume is required before matching jobs.' }) }))
const matchScore = (page: Page) => page.locator('.result-card', { hasText: 'MATCH SCORE' }).locator('strong')
const h1 = (page: Page) => page.locator('#main-content h1')

test.describe('Defect B: search relevance', () => {
  test('results are presented as a ranking with the raw score, never a percentage', async ({ page }) => {
    await registerViaApi(page, newAccount('search'))
    const query = 'Python backend developer internship'
    const searched = await page.request.get(`${API_URL}/api/jobs/search?q=${encodeURIComponent(query)}&top_k=10`)
    expect(searched.status()).toBe(200)
    const api = await searched.json() as Array<{ job_title: string; similarity_score: number }>
    expect(api.length).toBeGreaterThan(0)

    await page.goto('/careers')
    await page.getByRole('textbox', { name: 'Search opportunities' }).fill(query)
    await page.getByRole('button', { name: 'Search', exact: true }).click()
    const cards = page.locator('.comparison-card', { hasText: 'Search opportunities' }).locator('article.career-card')
    await expect(cards).toHaveCount(api.length)
    await expect(page.getByText('it has no fixed maximum and is not a match percentage')).toBeVisible()
    for (const [index, item] of api.entries()) {
      const card = cards.nth(index)
      await expect(card.getByRole('heading', { level: 3 })).toHaveText(item.job_title)
      await expect(card.locator('.match-badge')).toHaveText(`Rank ${index + 1} of ${api.length}`)
      await expect(card.getByText(`Similarity score ${item.similarity_score.toFixed(2)}`)).toBeVisible()
    }
    await expect(cards.locator('.match-badge').filter({ hasText: '%' })).toHaveCount(0)
  })
})

test.describe('Defect C: match score on job details', () => {
  test('a retrieved opportunity shows the score the backend calculated', async ({ page }) => {
    const resumeId = await accountWithProcessedResume(page)
    const top = (await jobMatches(page, resumeId, 20))[0]
    await page.goto(`/jobs/${top.job_id}`)
    await page.getByRole('button', { name: 'Check my match' }).click()
    await expect(matchScore(page)).toHaveText(`${Math.round(top.match_score)}%`)
    await page.locator('.result-card', { hasText: 'MATCH SCORE' }).scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'e2e/.tmp/screens/job-match-score.png', fullPage: true })
  })

  test('an opportunity outside the retrieved set says there is no score, not zero', async ({ page }) => {
    const resumeId = await accountWithProcessedResume(page)
    const retrieved = new Set((await jobMatches(page, resumeId, 20)).map((match) => match.job_id))
    const outside = Array.from({ length: 320 }, (_, index) => `JOB-${String(index + 1).padStart(4, '0')}`).find((id) => !retrieved.has(id))
    expect(outside).toBeDefined()
    await page.goto(`/jobs/${outside}`)
    await page.getByRole('button', { name: 'Check my match' }).click()
    await expect(page.getByText('No match score for this opportunity')).toBeVisible()
    await expect(page.getByText(`calculated only for the ${retrieved.size} opportunities retrieved as closest to your resume`)).toBeVisible()
    await expect(page.locator('.result-card', { hasText: 'MATCH SCORE' })).toHaveCount(0)
  })

  test('a failed match request is reported and can be retried', async ({ page, guard }) => {
    guard.allowStatus((url, status) => status === 409 && url.includes('/job-matches'))
    const resumeId = await accountWithProcessedResume(page)
    const top = (await jobMatches(page, resumeId, 20))[0]
    await failJobMatches(page)
    await page.goto(`/jobs/${top.job_id}`)
    await page.getByRole('button', { name: 'Check my match' }).click()
    const alert = page.getByRole('alert').filter({ hasText: 'A structured resume is required before matching jobs.' })
    await expect(alert).toBeVisible()
    await page.unroute('**/api/resumes/*/job-matches*')
    await alert.getByRole('button', { name: 'Retry' }).click()
    await expect(matchScore(page)).toHaveText(`${Math.round(top.match_score)}%`)
  })

  test("a slow match response for one job is never shown under another job", async ({ page }) => {
    const resumeId = await accountWithProcessedResume(page)
    const [jobA, jobB] = await jobMatches(page, resumeId, 20)
    expect(jobB, 'two retrieved opportunities').toBeDefined()

    await page.goto(`/jobs/${jobB.job_id}`)
    await expect(h1(page)).toHaveText(jobB.job_title)
    // Move to job A inside the same mounted view (as the browser's back/forward does).
    await page.evaluate((id) => { history.pushState({}, '', `/jobs/${id}`); dispatchEvent(new PopStateEvent('popstate')) }, jobA.job_id)
    await expect(h1(page)).toHaveText(jobA.job_title)

    const slow = await holdRequests(page, '**/api/resumes/*/job-matches*')
    await page.getByRole('button', { name: 'Check my match' }).click()
    await expect.poll(slow.count).toBe(1)                 // A's request is in flight...
    await page.evaluate(() => history.back())            // ...when the user returns to job B
    await expect(h1(page)).toHaveText(jobB.job_title)

    const aResponse = page.waitForResponse((response) => response.url().includes('/job-matches'))
    await slow.release()                                 // A's real response now arrives, after B
    await aResponse
    await staysAbsent(page.locator('.result-card', { hasText: 'MATCH SCORE' }))
    await staysAbsent(page.getByText(/No match score for this opportunity/))
    await expect(page.getByRole('button', { name: 'Check my match' })).toBeVisible()

    // B's own result still works afterwards.
    await page.getByRole('button', { name: 'Check my match' }).click()
    await expect(matchScore(page)).toHaveText(`${Math.round(jobB.match_score)}%`)
  })
})

test.describe('Defect E: learning roadmap context', () => {
  test('shows the top match and exactly its missing skills from the API', async ({ page }) => {
    const resumeId = await accountWithProcessedResume(page, 'marketing')
    const top = (await jobMatches(page, resumeId, 1))[0]
    expect(top.missing_required_skills.length, 'precondition: the marketing resume has gaps for its top match').toBeGreaterThan(0)
    await page.goto('/roadmap')
    const context = page.locator('section', { has: page.getByRole('heading', { level: 3, name: `From your top job match: ${top.job_title}, ${top.company}` }) })
    await expect(context).toBeVisible()
    await expect(context.locator('.warning-chip')).toHaveText(top.missing_required_skills)
  })

  test('a top match with no missing required skills says so instead of showing chips', async ({ page }) => {
    // Real data, no interception: the backend synthetic resume covers every required
    // skill of its top match.
    const resumeId = await accountWithProcessedResume(page, 'backend')
    const top = (await jobMatches(page, resumeId, 1))[0]
    expect(top.missing_required_skills, 'precondition: the backend resume has no gaps for its top match').toEqual([])
    await page.goto('/roadmap')
    const context = page.locator('section', { has: page.getByRole('heading', { level: 3, name: `From your top job match: ${top.job_title}, ${top.company}` }) })
    await expect(context.getByText('Your resume covers every required skill listed for this opportunity.')).toBeVisible()
    await expect(context.locator('.warning-chip')).toHaveCount(0)
  })

  test('a failure is shown instead of being swallowed, and Retry makes a new request', async ({ page, guard }) => {
    guard.allowStatus((url, status) => status === 409 && url.includes('/job-matches'))
    const resumeId = await accountWithProcessedResume(page)
    const top = (await jobMatches(page, resumeId, 1))[0]
    let failuresLeft = 1
    const requests: string[] = []
    await page.route('**/api/resumes/*/job-matches*', (route) => {
      requests.push(route.request().url())
      if (failuresLeft-- > 0) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'A structured resume is required before matching jobs.' }) })
      return route.continue()
    })
    await page.goto('/roadmap')
    const alert = page.getByRole('alert').filter({ hasText: 'A structured resume is required before matching jobs.' })
    await expect(alert).toBeVisible()
    await expect(page.getByText('CURRENT SKILL GAP CONTEXT')).toHaveCount(0)
    const requestsBeforeRetry = requests.length
    await alert.getByRole('button', { name: 'Retry' }).click()
    await expect(page.getByRole('heading', { level: 3, name: `From your top job match: ${top.job_title}, ${top.company}` })).toBeVisible()
    expect(requests.length).toBe(requestsBeforeRetry + 1)
    await expect(alert).toHaveCount(0)
  })
})

