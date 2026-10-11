import { readFileSync } from 'node:fs'
import path from 'node:path'
import { expect, test } from '@playwright/test'
import { API_URL } from './support/fixtures'

// The backend launcher writes what it actually resolved through the app's own settings
// code; this confirms the server under test is the isolated one.
test('backend under test uses the isolated database and no LLM provider', async ({ request }) => {
  const report = JSON.parse(readFileSync(path.resolve('e2e/.tmp/isolation.json'), 'utf8')) as { database_path: string; resume_storage_dir: string; checks: Record<string, boolean> }
  expect(report.checks).toEqual({ database_is_isolated: true, resume_store_is_isolated: true, llm_provider_is_null: true, embedding_download_disabled: true, process_guard_refuses_real_data_and_network: true })
  const tmpRoot = path.resolve('e2e/.tmp')
  expect(path.resolve(report.database_path).startsWith(tmpRoot)).toBe(true)
  expect(path.resolve(report.resume_storage_dir).startsWith(tmpRoot)).toBe(true)
  expect((await request.get(`${API_URL}/health`)).ok()).toBe(true)
})

// Every test gets a fresh browser context (no cookies, no stored session) pointed at the
// suite's own servers, never the developer's dev server on 5173 or API on 8000.
test('tests start signed out against the isolated servers only', async ({ page, baseURL, context }) => {
  expect(await context.cookies()).toEqual([])
  expect(new URL(baseURL ?? '').port).toBe('5174')
  expect(new URL(API_URL).port).toBe('8100')
  const apiRequests: string[] = []
  page.on('request', (request) => { if (request.url().includes('/api/')) apiRequests.push(new URL(request.url()).origin) })
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  expect(apiRequests.length).toBeGreaterThan(0)
  expect(new Set(apiRequests)).toEqual(new Set([API_URL]))
})
