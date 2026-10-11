import { API_URL, expect, newAccount, registerViaApi, test } from './support/fixtures'

// Opportunities search and job details on real API data; empty and error answers are
// injected in the browser only (the semantic search itself always returns its nearest results).
type JobPosting = { job_id: string; job_title: string; company: string; required_skills: string[]; location: string }

test.beforeEach(async ({ page }) => { await registerViaApi(page, newAccount('opps')) })

const search = async (page: import('@playwright/test').Page, query: string) => {
  await page.getByRole('textbox', { name: 'Search opportunities' }).fill(query)
  await page.getByRole('button', { name: 'Search', exact: true }).click()
}

test('an empty search answer is shown as an empty state', async ({ page }) => {
  await page.route('**/api/jobs/search*', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.goto('/careers')
  await search(page, 'underwater basket weaving')
  await expect(page.getByText('No opportunities matched that search.')).toBeVisible()
  await expect(page.locator('article.career-card')).toHaveCount(0)
})

test('a search error is reported and a new search recovers', async ({ page, guard }) => {
  guard.allowStatus((url, status) => status === 422 && url.includes('/api/jobs/search'))
  await page.route('**/api/jobs/search*', (route) => route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Search query must not be empty.' }) }))
  await page.goto('/careers')
  await search(page, 'data analyst')
  await expect(page.getByRole('alert')).toHaveText('Search query must not be empty.')
  await page.unroute('**/api/jobs/search*')
  await search(page, 'data analyst')
  await expect(page.locator('article.career-card').first()).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('job details show the real posting and can be added to the tracker', async ({ page }) => {
  const job = await (await page.request.get(`${API_URL}/api/jobs/JOB-0002`)).json() as JobPosting
  await page.goto('/careers')
  await search(page, job.job_title)
  const card = page.locator('article.career-card', { has: page.getByRole('heading', { name: job.job_title, exact: true }) }).first()
  await card.getByRole('button', { name: 'View details →' }).click()
  await expect(page.locator('#main-content h1')).toHaveText(/.+/)
  const posting = await (await page.request.get(`${API_URL}/api/jobs/${encodeURIComponent(new URL(page.url()).pathname.split('/').pop() ?? '')}`)).json() as JobPosting
  await expect(page.locator('#main-content h1')).toHaveText(posting.job_title)
  const requiredCard = page.locator('article', { hasText: 'REQUIRED SKILLS' })
  for (const skill of posting.required_skills) await expect(requiredCard.getByText(skill, { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: 'Opportunities', exact: true })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('button', { name: 'Add to Tracker' }).click()
  await expect(page.getByText(/Added to tracker/)).toBeVisible()
  const tracked = await (await page.request.get(`${API_URL}/api/applications`)).json() as Array<{ job_id: string }>
  expect(tracked.map((application) => application.job_id)).toContain(posting.job_id)
})
