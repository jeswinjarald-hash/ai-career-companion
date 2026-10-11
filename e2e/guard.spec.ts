import { expect, test, type Page } from '@playwright/test'
import { API_URL, WEB_URL, createNetworkGuard } from './support/fixtures'

// Regression tests for the network guard itself (it would otherwise fail silently).
// Uses the plain Playwright `test`, not the auto-guarded one, so each case can inspect
// exactly what the guard recorded. Failures are produced by real missing files on the
// Vite server or by browser-side request interception; no app code is changed.
const settle = (page: Page) => page.waitForTimeout(300)

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
})

test('a missing JavaScript module on the frontend server is reported', async ({ page }) => {
  const guard = await createNetworkGuard(page)
  await page.evaluate(() => new Promise<void>((resolve) => {
    const script = document.createElement('script'); script.type = 'module'; script.src = '/src/guard-probe-missing.js'
    script.onerror = () => resolve(); script.onload = () => resolve(); document.head.append(script)
  }))
  await settle(page)
  expect(guard.problems.some((problem) => problem.includes(`${WEB_URL}/src/guard-probe-missing.js`))).toBe(true)
})

test('a missing stylesheet on the frontend server is reported', async ({ page }) => {
  const guard = await createNetworkGuard(page)
  await page.evaluate(() => new Promise<void>((resolve) => {
    const link = document.createElement('link'); link.rel = 'stylesheet'; link.href = '/guard-probe-missing.css'
    link.onerror = () => resolve(); link.onload = () => resolve(); document.head.append(link)
  }))
  await settle(page)
  expect(guard.problems.some((problem) => problem.includes(`${WEB_URL}/guard-probe-missing.css`))).toBe(true)
})

test('an API 5xx is reported even if a test allowed that URL', async ({ page }) => {
  const guard = await createNetworkGuard(page)
  guard.allowStatus(() => true)
  await page.route(`${API_URL}/health`, (route) => route.fulfill({ status: 503, body: '{}' }))
  await page.evaluate((url) => fetch(url).catch(() => undefined), `${API_URL}/health`)
  await settle(page)
  expect(guard.problems.some((problem) => problem.startsWith('http 503'))).toBe(true)
})

test('an unexpected API 4xx is reported, and an explicitly allowed one is not', async ({ page }) => {
  const guard = await createNetworkGuard(page)
  await page.evaluate((url) => fetch(url, { credentials: 'include' }), `${API_URL}/api/applications/summary`)
  await settle(page)
  expect(guard.problems.filter((problem) => problem.includes('401'))).not.toEqual([])

  const allowing = await createNetworkGuard(page)
  allowing.allowStatus((url, status) => status === 401 && url === `${API_URL}/api/applications/summary`)
  await page.evaluate((url) => fetch(url, { credentials: 'include' }), `${API_URL}/api/applications/summary`)
  await settle(page)
  expect(allowing.problems).toEqual([])
})

test('a failed API request is reported', async ({ page }) => {
  const guard = await createNetworkGuard(page)
  await page.route(`${API_URL}/health`, (route) => route.abort('connectionrefused'))
  await page.evaluate((url) => fetch(url).catch(() => undefined), `${API_URL}/health`)
  await settle(page)
  expect(guard.problems.some((problem) => problem.startsWith(`requestfailed: GET ${API_URL}/health`))).toBe(true)
})

test('the logout quirk is accepted only when the logout request really got its 204', async ({ page }) => {
  const real = await createNetworkGuard(page)
  const status = await page.evaluate((url) => fetch(url, { method: 'POST', credentials: 'include' }).then((response) => response.status), `${API_URL}/api/auth/logout`)
  await settle(page)
  expect(status).toBe(204)
  expect(real.problems).toEqual([])

  const aborted = await createNetworkGuard(page)
  await page.route(`${API_URL}/api/auth/logout`, (route) => route.abort('aborted'))
  await page.evaluate((url) => fetch(url, { method: 'POST', credentials: 'include' }).catch(() => undefined), `${API_URL}/api/auth/logout`)
  await settle(page)
  expect(aborted.problems.some((problem) => problem.startsWith(`requestfailed: POST ${API_URL}/api/auth/logout`))).toBe(true)
})

test('requests to external hosts are blocked and reported', async ({ page }) => {
  const guard = await createNetworkGuard(page)
  const outcome = await page.evaluate(() => fetch('https://example.com/guard-probe').then(() => 'reached', () => 'blocked'))
  await settle(page)
  expect(outcome).toBe('blocked')
  expect(guard.problems.some((problem) => problem.startsWith('external request blocked: GET https://example.com/guard-probe'))).toBe(true)
})
