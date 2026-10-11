import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { API_URL, allowSignedOutCheck, expect, newAccount, registerViaApi, settleAnimations, test } from './support/fixtures'
import { jobMatches, processResumeViaApi } from './support/resumes'

// Automated WCAG 2.x A/AA checks (axe-core) on every redesigned screen, with real data.
// Automated scans catch only part of WCAG; keyboard operation is covered separately
// (navigation.spec.ts drawer test, focus-on-navigation assertions).
const wcagViolations = async (page: Page) => {
  // Entry transitions briefly render content semi-transparent; scan the settled page.
  await settleAnimations(page)
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()
  return violations.map((item) => `${item.impact} ${item.id}: ${item.nodes.length} node(s) e.g. ${item.nodes[0]?.target.join(' ')}`)
}

test('sign-in and sign-up screens have no WCAG A/AA violations', async ({ page, guard }) => {
  allowSignedOutCheck(guard)
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  expect(await wcagViolations(page)).toEqual([])
  await page.goto('/signup')
  await expect(page.getByRole('button', { name: 'Create account' })).toBeVisible()
  expect(await wcagViolations(page)).toEqual([])
})

test('new-user screens have no WCAG A/AA violations', async ({ page }) => {
  await registerViaApi(page, newAccount('a11y-new'))
  for (const [path, ready] of [['/dashboard', 'No resume uploaded yet'], ['/resume', 'Upload your resume'], ['/careers', 'Search opportunities']] as const) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: ready }).first()).toBeVisible()
    expect(await wcagViolations(page), path).toEqual([])
  }
})

test('screens with an analysed resume have no WCAG A/AA violations', async ({ page }) => {
  test.setTimeout(240_000)
  const profileId = await registerViaApi(page, newAccount('a11y-full'))
  const resumeId = await processResumeViaApi(page, profileId, 'marketing')
  const [top] = await jobMatches(page, resumeId, 1)
  expect((await page.request.post(`${API_URL}/api/applications`, { data: { job_id: top.job_id } })).status()).toBe(201)
  const screens: Array<[string, (p: Page) => Promise<void>]> = [
    ['/dashboard', (p) => expect(p.locator('.match-row').first()).toBeVisible({ timeout: 60_000 })],
    ['/resume', (p) => expect(p.getByText('Active resume · analysed')).toBeVisible()],
    ['/resume/results', (p) => expect(p.getByRole('heading', { name: 'EXTRACTED SKILLS' })).toBeVisible()],
    ['/careers', (p) => expect(p.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 })],
    [`/jobs/${top.job_id}`, (p) => expect(p.locator('#main-content h1')).toHaveText(top.job_title)],
    [`/skills?job=${top.job_id}`, (p) => expect(p.getByRole('figure').filter({ hasText: 'How readiness is calculated' })).toBeVisible({ timeout: 60_000 })],
    ['/applications', (p) => expect(p.locator('.application-card').first()).toBeVisible()],
    ['/roadmap', (p) => expect(p.getByText('CURRENT SKILL GAP CONTEXT')).toBeVisible({ timeout: 60_000 })],
    [`/interview-prep?job=${top.job_id}`, (p) => expect(p.locator('#main-content h1')).toBeVisible()],
    ['/assistant', (p) => expect(p.getByText('Ask me anything about your career search.')).toBeVisible()],
    ['/profile', (p) => expect(p.getByLabel('Full name')).toBeVisible()],
    ['/progress', (p) => expect(p.locator('.stat-card').first()).toBeVisible()],
    ['/settings', (p) => expect(p.locator('.setting-row').first()).toBeVisible()],
  ]
  for (const [path, ready] of screens) {
    await page.goto(path)
    await ready(page)
    expect(await wcagViolations(page), path).toEqual([])
  }
})

test('the open mobile navigation drawer has no WCAG A/AA violations', async ({ page }) => {
  await registerViaApi(page, newAccount('a11y-drawer'))
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/dashboard')
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  await expect(page.getByRole('dialog', { name: 'Navigation menu' })).toBeVisible()
  expect(await wcagViolations(page)).toEqual([])
})


