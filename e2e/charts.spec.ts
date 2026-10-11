import { API_URL, expect, newAccount, registerViaApi, test } from './support/fixtures'
import { jobMatches, processResumeViaApi } from './support/resumes'

// Charts must show exactly what the API returned. Each test reads the source data from
// the isolated backend and compares every rendered row against it.
type ScoreComponent = { component: string; label: string; weight: number; included: boolean; score: number | null; matched: number; total: number }
type SkillGap = { summary: { overall_readiness: number; score_breakdown: ScoreComponent[] } }

test('skill-gap readiness chart matches the backend breakdown, row by row', async ({ page }) => {
  test.setTimeout(120_000)
  const profileId = await registerViaApi(page, newAccount('readiness'))
  const resumeId = await processResumeViaApi(page, profileId, 'marketing')
  const [top] = await jobMatches(page, resumeId, 1)

  await page.goto(`/skills?job=${encodeURIComponent(top.job_id)}`)
  const chart = page.getByRole('figure').filter({ hasText: 'How readiness is calculated' })
  await expect(chart).toBeVisible({ timeout: 60_000 })
  const persisted = await page.request.get(`${API_URL}/api/resumes/${resumeId}/skill-gap/${encodeURIComponent(top.job_id)}`)
  expect(persisted.status()).toBe(200)
  const { summary } = await persisted.json() as SkillGap

  await expect(page.locator('.skill-score-card strong')).toHaveText(`${summary.overall_readiness}%`)
  const rows = chart.locator('tbody tr')
  await expect(rows).toHaveCount(summary.score_breakdown.length)
  for (const [index, component] of summary.score_breakdown.entries()) {
    const row = rows.nth(index)
    await expect(row.locator('th')).toHaveText(component.label)
    const assessed = component.included && component.score !== null
    await expect(row.locator('td.meter-value')).toHaveText(assessed ? `${Math.round((component.score as number) * 100)}%` : '—')
    await expect(row.locator('td.meter-detail')).toContainText(`${Math.round(component.weight * 100)}% weight`)
    if (!assessed) await expect(row.getByText('Not available')).toBeVisible()
  }
  // The headline equals the weighted mean of the assessed components the chart displays.
  const assessed = summary.score_breakdown.filter((component) => component.included && component.score !== null)
  const weight = assessed.reduce((sum, component) => sum + component.weight, 0)
  const recomputed = weight === 0 ? 0 : Math.round(assessed.reduce((sum, component) => sum + (component.score as number) * component.weight, 0) / weight * 100)
  expect(recomputed).toBe(summary.overall_readiness)
})

test('application status chart is absent with no data and exact with real applications', async ({ page }) => {
  await registerViaApi(page, newAccount('status-chart'))
  await page.goto('/dashboard')
  const activity = page.locator('section', { has: page.getByRole('heading', { name: 'From your application tracker' }) })
  await expect(activity.getByText('No applications tracked yet.', { exact: false })).toBeVisible()
  await expect(activity.getByRole('figure')).toHaveCount(0)

  for (const jobId of ['JOB-0001', 'JOB-0002', 'JOB-0003']) expect((await page.request.post(`${API_URL}/api/applications`, { data: { job_id: jobId } })).status()).toBe(201)
  const list = await (await page.request.get(`${API_URL}/api/applications`)).json() as Array<{ id: number }>
  expect((await page.request.patch(`${API_URL}/api/applications/${list[0].id}`, { data: { status: 'applied', applied_date: '2026-09-01' } })).status()).toBe(200)
  const summary = await (await page.request.get(`${API_URL}/api/applications/summary`)).json() as { total_applications: number; status_counts: Record<string, number> }

  await page.reload()
  const chart = activity.getByRole('figure').filter({ hasText: 'Applications by status' })
  await expect(chart).toContainText(`${summary.total_applications} tracked applications`)
  const nonZero = Object.entries(summary.status_counts).filter(([, count]) => count > 0)
  await expect(chart.locator('tbody tr')).toHaveCount(nonZero.length)
  await expect(chart.locator('tbody tr', { hasText: 'Saved' }).locator('td.meter-value')).toHaveText(String(summary.status_counts.saved))
  await expect(chart.locator('tbody tr', { hasText: 'Applied' }).locator('td.meter-value')).toHaveText(String(summary.status_counts.applied))
})
