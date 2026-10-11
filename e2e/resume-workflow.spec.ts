import type { Page } from '@playwright/test'
import { API_URL, expect, newAccount, registerViaApi, test } from './support/fixtures'
import { SYNTHETIC_RESUMES, holdRequests, jobMatches, processResumeViaApi } from './support/resumes'

// Resume Studio and Overview, end to end on the isolated backend with synthetic resumes.
// Expected values are read from the real API in the same test. Failures are injected only
// in the browser (route.fulfill with 4xx answers the backend genuinely uses).
const h1 = (page: Page) => page.locator('#main-content h1')
const sidebar = (page: Page, label: string) => page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: label, exact: true })
const banner = (page: Page, title: RegExp) => page.getByRole('heading', { level: 2, name: title })
const DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

type Structured = { data: { skills: string[]; education: unknown[]; experience: unknown[]; internships: unknown[]; projects: unknown[] } }

test('uploading a synthetic resume produces real results on Resume Studio and Overview', async ({ page }) => {
  test.setTimeout(180_000)
  const profileId = await registerViaApi(page, newAccount('upload'))
  await page.goto('/resume')
  await expect(page.getByRole('heading', { level: 2, name: 'Upload your resume' })).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles(SYNTHETIC_RESUMES.backend)
  await expect(page.getByText('synthetic-resume.docx')).toBeVisible()
  await page.getByRole('button', { name: 'Upload and analyse' }).click()

  await expect(page).toHaveURL(/\/resume\/results$/, { timeout: 120_000 })
  await expect(h1(page)).toHaveText('What we extracted from your resume.')
  const resumes = await (await page.request.get(`${API_URL}/api/profiles/${profileId}/resumes`)).json() as Array<{ id: number }>
  const resumeId = resumes[0].id
  const structured = await (await page.request.get(`${API_URL}/api/resumes/${resumeId}/structured`)).json() as Structured
  const skillsCard = page.locator('article', { has: page.getByRole('heading', { name: 'EXTRACTED SKILLS' }) })
  for (const skill of structured.data.skills) await expect(skillsCard.getByText(skill, { exact: true }).first()).toBeVisible()
  await expect(page.locator('.coverage-list li.found', { hasText: 'Skills' })).toBeVisible()

  await sidebar(page, 'Overview').click()
  await expect(banner(page, /^Resume analysed/)).toBeVisible()
  const kpis = page.locator('.kpi-strip')
  await expect(kpis.locator('div', { hasText: 'Skills' }).locator('dd')).toHaveText(String(structured.data.skills.length))
  await expect(kpis.locator('div', { hasText: 'Projects' }).locator('dd')).toHaveText(String(structured.data.projects.length))
  await expect(kpis.locator('div', { hasText: 'Experience' }).locator('dd')).toHaveText(String(structured.data.experience.length + structured.data.internships.length))

  const top = await jobMatches(page, resumeId, 5)
  const rows = page.locator('.match-row')
  await expect(rows).toHaveCount(top.length, { timeout: 60_000 })
  for (const [index, match] of top.entries()) {
    await expect(rows.nth(index).locator('strong')).toHaveText(match.job_title)
    await expect(rows.nth(index).locator('.match-score b')).toHaveText(`${Math.round(match.match_score)}%`)
  }

  // Persisted, not held in the page: a full reload restores the same state from the API.
  await page.reload()
  await expect(banner(page, /^Resume analysed/)).toBeVisible()
  await expect(page.locator('.match-row').first().locator('strong')).toHaveText(top[0].job_title)
})

test('unsupported, empty and oversized files are refused before upload', async ({ page }) => {
  await registerViaApi(page, newAccount('invalid'))
  const uploads: string[] = []
  page.on('request', (request) => { if (request.method() === 'POST' && /\/api\/profiles\/\d+\/resumes$/.test(request.url())) uploads.push(request.url()) })
  await page.goto('/resume')
  const input = page.locator('input[type="file"]')
  await input.setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('plain text') })
  await expect(page.getByRole('alert')).toHaveText('That file type is not supported. Please choose a PDF or DOCX resume.')
  await input.setInputFiles({ name: 'empty.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(0) })
  await expect(page.getByRole('alert')).toHaveText('That file is empty. Please choose a different resume file.')
  await input.setInputFiles({ name: 'huge.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 0x20) })
  await expect(page.getByRole('alert')).toContainText('Resumes must be 10 MB or smaller.')
  await expect(page.getByRole('button', { name: 'Upload and analyse' })).toHaveCount(0)
  expect(uploads).toEqual([])
})

test('a file whose content is not really a PDF is rejected by the server, and the active resume stays', async ({ page, guard }) => {
  guard.allowStatus((url, status) => status === 400 && /\/api\/profiles\/\d+\/resumes$/.test(url))
  const profileId = await registerViaApi(page, newAccount('server-reject'))
  await processResumeViaApi(page, profileId, 'backend')
  await page.goto('/resume')
  await expect(page.getByText('Active resume · analysed')).toBeVisible()
  await page.locator('input[type="file"]').setInputFiles({ name: 'disguised.pdf', mimeType: 'application/pdf', buffer: Buffer.from('this is not a pdf') })
  await page.getByRole('button', { name: 'Upload and analyse new resume' }).click()
  const alert = page.getByRole('alert').filter({ hasText: 'Upload not accepted.' })
  await expect(alert).toContainText('The file extension does not match the uploaded file content.')
  await expect(page.getByText('Active resume · analysed')).toBeVisible()
  await expect(page.getByText('synthetic-resume.docx')).toBeVisible()
  await sidebar(page, 'Overview').click()
  await expect(banner(page, /^Resume analysed/)).toBeVisible()
})

test('an analysis failure is explained and can be retried from Overview', async ({ page, guard }) => {
  guard.allowStatus((url, status) => status === 409 && url.endsWith('/extract-text'))
  await registerViaApi(page, newAccount('retry'))
  let failuresLeft = 1
  await page.route('**/api/resumes/*/extract-text', (route) => failuresLeft-- > 0
    ? route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Text extraction failed for this file.' }) })
    : route.continue())
  await page.goto('/resume')
  await page.locator('input[type="file"]').setInputFiles(SYNTHETIC_RESUMES.backend)
  await page.getByRole('button', { name: 'Upload and analyse' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Analysis failed.' })).toContainText('Text extraction failed for this file.')
  await expect(page.locator('.processing-step.failed')).toHaveText(/Extract text/)
  await expect(page.getByRole('button', { name: 'Retry analysis' })).toBeVisible()

  await sidebar(page, 'Overview').click()
  await expect(banner(page, /^Analysis failed/)).toBeVisible()
  await page.getByRole('button', { name: 'Retry analysis' }).click()
  await expect(banner(page, /^Resume analysed/)).toBeVisible({ timeout: 120_000 })
})

test('a resume that was uploaded but never analysed is offered for analysis, not reported as failed', async ({ page, guard }) => {
  // GET /structured answers 404 until a resume has been analysed; the app reads that as "no results yet".
  guard.allowStatus((url, status) => status === 404 && /\/api\/resumes\/\d+\/structured$/.test(url))
  const profileId = await registerViaApi(page, newAccount('awaiting'))
  const uploaded = await page.request.post(`${API_URL}/api/profiles/${profileId}/resumes`, { multipart: { file: { name: 'stored-resume.docx', mimeType: DOCX_TYPE, buffer: (await import('node:fs')).readFileSync(SYNTHETIC_RESUMES.backend) } } })
  expect(uploaded.status()).toBe(201)
  await page.goto('/dashboard')
  await expect(banner(page, /^Awaiting analysis/)).toBeVisible()
  await expect(page.getByText(/stored-resume\.docx was uploaded/)).toBeVisible()
  await page.getByRole('button', { name: 'Analyse now' }).click()
  await expect(banner(page, /^Resume analysed/)).toBeVisible({ timeout: 120_000 })
})

test('replacing a resume never shows the previous results as the new ones', async ({ page }) => {
  test.setTimeout(180_000)
  const profileId = await registerViaApi(page, newAccount('replace'))
  await processResumeViaApi(page, profileId, 'backend')
  await page.goto('/resume')
  await page.locator('input[type="file"]').setInputFiles(SYNTHETIC_RESUMES.marketing)
  const slow = await holdRequests(page, '**/api/resumes/*/structure')
  await page.getByRole('button', { name: 'Upload and analyse new resume' }).click()
  await expect.poll(slow.count).toBe(1)

  // Mid-replacement: the old resume's results are no longer presented anywhere.
  await sidebar(page, 'Overview').click()
  await expect(banner(page, /^Analysing synthetic-resume-marketing\.docx/)).toBeVisible()
  await expect(page.locator('.match-row')).toHaveCount(0)
  await expect(page.locator('.kpi-strip')).toHaveCount(0)
  await slow.release()
  await expect(page).toHaveURL(/\/resume\/results$/, { timeout: 120_000 })   // the app opens the new results when done
  await expect(page.locator('#main-content').getByText('synthetic-resume-marketing.docx', { exact: true })).toBeVisible()
  await sidebar(page, 'Overview').click()
  await expect(banner(page, /^Resume analysed/)).toBeVisible()
  await expect(page.getByText(/synthetic-resume-marketing\.docx · analysed/)).toBeVisible()

  const resumes = await (await page.request.get(`${API_URL}/api/profiles/${profileId}/resumes`)).json() as Array<{ id: number; original_filename: string }>
  expect(resumes[0].original_filename).toBe('synthetic-resume-marketing.docx')
  const top = await jobMatches(page, resumes[0].id, 5)
  await expect(page.locator('.match-row').first().locator('strong')).toHaveText(top[0].job_title, { timeout: 60_000 })
})

test('Overview handles a resume-status load error and recovers with Try again', async ({ page, guard }) => {
  guard.allowStatus((url, status) => status === 409 && /\/api\/profiles\/\d+\/resumes$/.test(url))
  await registerViaApi(page, newAccount('load-error'))
  await page.route(/\/api\/profiles\/\d+\/resumes$/, (route) => route.request().method() === 'GET'
    ? route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'Resume service is temporarily unavailable.' }) })
    : route.continue())
  await page.goto('/dashboard')
  await expect(banner(page, /^Couldn’t load your resume status/)).toBeVisible()
  await expect(page.getByText('Resume service is temporarily unavailable.')).toBeVisible()
  await expect(banner(page, /^Analysis failed/)).toHaveCount(0)
  await page.unroute(/\/api\/profiles\/\d+\/resumes$/)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(banner(page, /^No resume uploaded yet/)).toBeVisible()
})

test('Overview top matches: an API error is shown with Retry, and Retry recovers', async ({ page, guard }) => {
  guard.allowStatus((url, status) => status === 409 && url.includes('/job-matches'))
  const profileId = await registerViaApi(page, newAccount('matches-error'))
  const resumeId = await processResumeViaApi(page, profileId, 'backend')
  const top = await jobMatches(page, resumeId, 5)
  // Fails until removed: development StrictMode mounts the module twice, so a one-shot
  // failure would land on the discarded first request.
  await page.route('**/api/resumes/*/job-matches*', (route) =>
    route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'A structured resume is required before matching jobs.' }) }))
  await page.goto('/dashboard')
  const module = page.locator('section', { has: page.getByRole('heading', { name: 'Top matches for your resume' }) })
  await expect(module.getByRole('alert')).toContainText('A structured resume is required before matching jobs.')
  await page.unroute('**/api/resumes/*/job-matches*')
  await module.getByRole('button', { name: 'Retry' }).click()
  await expect(module.locator('.match-row')).toHaveCount(top.length)
})
