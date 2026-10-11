import { mkdirSync } from 'node:fs'
import path from 'node:path'
import type { Page } from '@playwright/test'
import { API_URL, expect, newAccount, registerViaApi, settleAnimations, test } from './support/fixtures'
import { jobMatches, processResumeViaApi } from './support/resumes'
import { outOfBounds } from './support/layout'

// Every screen at phone, large-phone, tablet, laptop and desktop widths: no horizontal
// page overflow, and the primary navigation stays reachable. Full-page screenshots are
// written to e2e/.tmp/screens (gitignored) for visual review.
const WIDTHS = [320, 375, 390, 768, 1024, 1440]
const SCREENS_DIR = path.resolve('e2e/.tmp/screens')


async function checkWidths(page: Page, name: string, url: string, ready: (p: Page) => Promise<void>) {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(url)
    await ready(page)
    await page.evaluate(() => document.fonts.ready)
    await settleAnimations(page)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow, `${name} at ${width}px overflows horizontally by ${overflow}px`).toBeLessThanOrEqual(0)
    expect(await outOfBounds(page), `${name} at ${width}px has clipped or spilling content`).toEqual([])
    if (width < 960) await expect(page.getByRole('button', { name: 'Open navigation menu' })).toBeVisible()
    else await expect(page.getByRole('complementary', { name: 'Sidebar' })).toBeVisible()
    await page.screenshot({ path: path.join(SCREENS_DIR, `${name}-${width}.png`), fullPage: true })
  }
}

test.beforeAll(() => { mkdirSync(SCREENS_DIR, { recursive: true }) })

test('new user: overview, resume studio and sign-in fit every width', async ({ page }) => {
  test.setTimeout(180_000)
  await registerViaApi(page, newAccount('resp-new'))
  await checkWidths(page, 'overview-new', '/dashboard', (p) => expect(p.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible())
  await checkWidths(page, 'resume-new', '/resume', (p) => expect(p.getByRole('heading', { level: 2, name: 'Upload your resume' })).toBeVisible())
})

test('analysed resume: every screen fits every width', async ({ page }) => {
  test.setTimeout(480_000)
  const profileId = await registerViaApi(page, newAccount('resp-full'))
  const resumeId = await processResumeViaApi(page, profileId, 'marketing')
  const [top] = await jobMatches(page, resumeId, 1)
  expect((await page.request.post(`${API_URL}/api/applications`, { data: { job_id: top.job_id } })).status()).toBe(201)
  await checkWidths(page, 'overview', '/dashboard', (p) => expect(p.locator('.match-row').first()).toBeVisible({ timeout: 60_000 }))
  await checkWidths(page, 'resume', '/resume', (p) => expect(p.getByText('Active resume · analysed')).toBeVisible())
  await checkWidths(page, 'results', '/resume/results', (p) => expect(p.getByRole('heading', { name: 'EXTRACTED SKILLS' })).toBeVisible())
  await checkWidths(page, 'opportunities', '/careers', (p) => expect(p.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 }))
  await checkWidths(page, 'job', `/jobs/${top.job_id}`, (p) => expect(p.locator('#main-content h1')).toHaveText(top.job_title))
  await checkWidths(page, 'skills', `/skills?job=${top.job_id}`, (p) => expect(p.getByRole('figure').filter({ hasText: 'How readiness is calculated' })).toBeVisible({ timeout: 60_000 }))
  await checkWidths(page, 'applications', '/applications', (p) => expect(p.locator('.application-card').first()).toBeVisible())
  await checkWidths(page, 'roadmap', '/roadmap', (p) => expect(p.getByText('CURRENT SKILL GAP CONTEXT')).toBeVisible({ timeout: 60_000 }))
  await checkWidths(page, 'interview', `/interview-prep?job=${top.job_id}`, (p) => expect(p.locator('#main-content h1')).toBeVisible())
  await checkWidths(page, 'assistant', '/assistant', (p) => expect(p.getByText('Ask me anything about your career search.')).toBeVisible())
  await checkWidths(page, 'profile', '/profile', (p) => expect(p.getByLabel('Full name')).toBeVisible())
})
