import type { Page } from '@playwright/test'
import { API_URL, expect, fillSecret, newAccount, registerViaApi, test, type TestAccount } from './support/fixtures'

// Defect A regression: when a session expires mid-use and the user signs in again on the
// same URL, the job / application selected by that URL must be restored — previously the
// view came back but the selection had been cleared ("Opportunity not available." /
// "Application not found."). The expiry is real: the cookie is removed and the next
// authenticated request the page makes gets a 401 from the backend.
const JOB_ID = 'JOB-0001'
const SESSION_EXPIRED = 'Your session has expired. Please sign in again.'
const h1 = (page: Page) => page.locator('#main-content h1')

async function expireSessionOnReturn(page: Page) {
  await page.context().clearCookies()
  await page.goBack()
  await expect(page.getByRole('status').filter({ hasText: SESSION_EXPIRED })).toBeVisible()
}

async function signIn(page: Page, account: TestAccount) {
  await page.getByLabel('Email address').fill(account.email)
  await fillSecret(page.getByLabel('Password'), account.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

test.beforeEach(({ guard }) => {
  guard.allowStatus((url, status) => status === 401 && url.includes('/api/applications'))
})

test('signing in again after expiry restores the selected job', async ({ page }) => {
  const account = newAccount('expiry-job')
  await registerViaApi(page, account)
  const job = await (await page.request.get(`${API_URL}/api/jobs/${JOB_ID}`)).json() as { job_title: string }

  await page.goto(`/jobs/${JOB_ID}`)
  await expect(h1(page)).toHaveText(job.job_title)
  await expect(page.getByRole('button', { name: 'Add to Tracker' })).toBeVisible()
  await page.getByRole('button', { name: 'Back to search →' }).click()
  await expect(page).toHaveURL(/\/careers$/)

  await expireSessionOnReturn(page)
  await expect(page).toHaveURL(new RegExp(`/jobs/${JOB_ID}$`))
  await signIn(page, account)
  await expect(h1(page)).toHaveText(job.job_title)
})

test('signing in again after expiry restores the selected application', async ({ page }) => {
  const account = newAccount('expiry-app')
  await registerViaApi(page, account)
  const created = await page.request.post(`${API_URL}/api/applications`, { data: { job_id: JOB_ID } })
  expect(created.status()).toBe(201)
  const application = await created.json() as { id: number; job_title: string }

  await page.goto(`/applications/${application.id}`)
  await expect(h1(page)).toHaveText(application.job_title)
  await page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: 'Overview', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)

  await expireSessionOnReturn(page)
  await expect(page).toHaveURL(new RegExp(`/applications/${application.id}$`))
  await signIn(page, account)
  await expect(h1(page)).toHaveText(application.job_title)
})

test('a different user signing in on that URL still cannot see the application', async ({ page, guard }) => {
  guard.allowStatus((url, status) => status === 404 && /\/api\/applications\/\d+$/.test(url))
  const owner = newAccount('owner')
  await registerViaApi(page, owner)
  const ownerCreate = await page.request.post(`${API_URL}/api/applications`, { data: { job_id: JOB_ID } })
  expect(ownerCreate.status()).toBe(201)
  const application = await ownerCreate.json() as { id: number }

  await page.goto(`/applications/${application.id}`)
  await page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: 'Overview', exact: true }).click()
  await expireSessionOnReturn(page)

  const intruder = newAccount('intruder')
  await registerViaApi(page, intruder)
  await page.context().clearCookies()
  await signIn(page, intruder)
  await expect(h1(page)).toHaveText('Application not found.')
})
