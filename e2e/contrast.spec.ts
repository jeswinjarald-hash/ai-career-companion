import { API_URL, expect, newAccount, registerViaApi, test } from './support/fixtures'
import { jobMatches, processResumeViaApi } from './support/resumes'

import { measure } from './support/contrast'

// Measured WCAG AA text contrast on every screen (method documented in support/contrast.ts).
test('every visible text element meets WCAG AA contrast on the real rendered theme', async ({ page }) => {
  test.setTimeout(300_000)
  const profileId = await registerViaApi(page, newAccount('contrast'))
  const resumeId = await processResumeViaApi(page, profileId, 'marketing')
  const [top] = await jobMatches(page, resumeId, 1)
  expect((await page.request.post(`${API_URL}/api/applications`, { data: { job_id: top.job_id } })).status()).toBe(201)
  const screens: Array<[string, string]> = [
    ['/dashboard', '.match-row'], ['/resume', '.drop-zone'], ['/resume/results', '.coverage-list'], ['/careers', '.match-badge'],
    [`/jobs/${top.job_id}`, '.fact-list'], [`/skills?job=${top.job_id}`, '.score-ring'], ['/applications', '.application-card'],
    ['/roadmap', '.warning-chip'], ['/assistant', '.starter-prompts'], ['/profile', '.form-grid'], ['/progress', '.stat-card'], ['/settings', '.setting-row'],
  ]
  const failures: string[] = []
  for (const [path, ready] of screens) {
    await page.goto(path)
    await expect(page.locator(ready).first()).toBeVisible({ timeout: 60_000 })
    failures.push(...await measure(page, path))
  }
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/dashboard')
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  await expect(page.getByRole('dialog', { name: 'Navigation menu' })).toBeVisible()
  failures.push(...await measure(page, 'mobile drawer'))
  expect(failures).toEqual([])
})

test('signed-out screens meet WCAG AA contrast', async ({ page, guard }) => {
  guard.allowStatus((url, status) => status === 401 && url.endsWith('/api/auth/me'))
  const failures: string[] = []
  for (const path of ['/', '/signup']) {
    await page.goto(path)
    await expect(page.locator('.auth-form')).toBeVisible()
    failures.push(...await measure(page, path))
  }
  expect(failures).toEqual([])
})

// The pointer spotlight brightens the surface under the cursor; text must stay readable in
// that lit state too. The pointer is left resting on the card while it is measured.
test('text on pointer-lit cards still meets WCAG AA contrast', async ({ page }) => {
  test.setTimeout(240_000)
  const profileId = await registerViaApi(page, newAccount('contrast-lit'))
  await processResumeViaApi(page, profileId, 'backend')
  const failures: string[] = []
  const hoverAndMeasure = async (path: string, selector: string, label: string) => {
    await page.goto(path)
    const card = page.locator(selector).first()
    await expect(card).toBeVisible({ timeout: 60_000 })
    const box = await card.boundingBox()
    await page.mouse.move(box!.x + Math.min(160, box!.width / 2), box!.y + Math.min(60, box!.height / 2))
    await expect(card).toHaveClass(/\bis-lit\b/)
    failures.push(...await measure(page, label))
  }
  await hoverAndMeasure('/dashboard', '.state-banner', 'dashboard (banner lit)')
  await hoverAndMeasure('/dashboard', 'section.module', 'dashboard (top matches lit)')
  await hoverAndMeasure('/careers', 'article.career-card', 'opportunities (card lit)')
  await hoverAndMeasure('/resume', '.upload-card', 'resume studio (upload lit)')
  expect(failures).toEqual([])
})
