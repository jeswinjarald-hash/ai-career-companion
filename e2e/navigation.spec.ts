import type { Page } from '@playwright/test'
import { expect, fillSecret, newAccount, registerViaApi, test } from './support/fixtures'

const DESTINATIONS: Array<{ label: string; path: string }> = [
  { label: 'Resume Studio', path: '/resume' },
  { label: 'Opportunities', path: '/careers' },
  { label: 'Applications', path: '/applications' },
  { label: 'Skill Gaps', path: '/skills' },
  { label: 'Learning Roadmap', path: '/roadmap' },
  { label: 'Interview Prep', path: '/interview-prep' },
  { label: 'Career Assistant', path: '/assistant' },
  { label: 'Profile', path: '/profile' },
  { label: 'Progress', path: '/progress' },
  { label: 'Settings', path: '/settings' },
  { label: 'Overview', path: '/dashboard' },
]
const sidebarItem = (page: Page, label: string) => page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: label, exact: true })

test.beforeEach(async ({ page }) => {
  await registerViaApi(page, newAccount('nav'))
})

test('every destination opens from the sidebar, is marked current, and supports back navigation', async ({ page }) => {
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
  for (const { label, path } of DESTINATIONS) {
    await sidebarItem(page, label).click()
    await expect(page).toHaveURL(new RegExp(`${path}$`))
    await expect(page.locator('#main-content h1')).toBeVisible()
    await expect(page.locator('#main-content h1')).toBeFocused()
    await expect(sidebarItem(page, label)).toHaveAttribute('aria-current', 'page')
  }
  await page.goBack()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.locator('#main-content h1')).toHaveText('Keep your workspace focused.')
})

test('a direct deep link opens the requested page after the session check', async ({ page }) => {
  await page.goto('/careers')
  await expect(page.locator('#main-content h1')).toHaveText('Paths that fit your profile.')
  await expect(page.getByText('Process a resume to see opportunities ranked for you.')).toBeVisible()
})

test('empty states without a resume are honest', async ({ page }) => {
  await page.goto('/skills')
  await expect(page.getByText('Upload and process your resume before running skill gap analysis.')).toBeVisible()
  await page.goto('/progress')
  await expect(page.locator('.stat-card', { hasText: 'Resume analyzed' }).locator('strong')).toHaveText('No')
  // Defect D: a new account has only its name and e-mail, which do not count as completion.
  await expect(page.locator('.stat-card', { hasText: 'Profile completion' }).locator('strong')).toHaveText('0%')
  await expect(page.locator('.stat-card', { hasText: 'Profile completion' }).locator('small')).toHaveText('0 of 8 profile details saved')
  await page.goto('/profile')
  await expect(page.locator('.completion-label')).toHaveText('0% complete')
  await page.getByLabel('Degree').fill('B.Tech')
  await page.getByLabel('Skills').fill('Python, SQL')
  await expect(page.locator('.completion-label')).toHaveText('25% complete')
})

test('the profile form saves real data and the dashboard reflects it', async ({ page }) => {
  await page.goto('/profile')
  await page.getByLabel('Degree').fill('B.Tech')
  await page.getByLabel('Target roles').fill('Backend Developer, Data Analyst')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Profile saved.' })).toBeVisible()
  await page.reload()
  await expect(page.getByLabel('Degree')).toHaveValue('B.Tech')
  await sidebarItem(page, 'Overview').click()
  const profileModule = page.locator('section', { has: page.getByRole('heading', { name: 'Profile details' }) })
  await expect(profileModule).toContainText('2 of 8 details saved')
  await expect(profileModule).toContainText('Target roles: Backend Developer, Data Analyst')
})

test.describe('small screens', () => {
  test.beforeEach(async ({ page }) => { await page.setViewportSize({ width: 375, height: 812 }) })

  test('the menu opens a drawer that reaches every destination without horizontal scroll', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('complementary', { name: 'Sidebar' })).toBeHidden()
    const menu = page.getByRole('button', { name: 'Open navigation menu' })
    await menu.click()
    const drawer = page.getByRole('dialog', { name: 'Navigation menu' })
    await expect(drawer).toBeVisible()
    await expect(menu).toHaveAttribute('aria-expanded', 'true')
    for (const { label } of DESTINATIONS) await expect(drawer.getByRole('button', { name: label, exact: true })).toHaveCount(1)
    await drawer.getByRole('button', { name: 'Settings', exact: true }).click()
    await expect(drawer).toBeHidden()
    await expect(page).toHaveURL(/\/settings$/)
    await expect(page.locator('#main-content h1')).toBeFocused()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(overflow).toBeLessThanOrEqual(0)
  })

  test('the drawer is keyboard operable: focus moves in, Tab is contained, Escape returns focus', async ({ page }) => {
    await page.goto('/dashboard')
    const menu = page.getByRole('button', { name: 'Open navigation menu' })
    await menu.focus()
    await page.keyboard.press('Enter')
    const drawer = page.getByRole('dialog', { name: 'Navigation menu' })
    await expect(drawer.getByRole('button', { name: 'Close navigation menu' })).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(drawer.getByRole('button', { name: 'Settings', exact: true })).toBeFocused()   // wrapped to the last item
    await page.keyboard.press('Tab')
    await expect(drawer.getByRole('button', { name: 'Close navigation menu' })).toBeFocused()   // and back to the first
    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    await expect(menu).toBeFocused()
  })

  test('sign-in works on a small screen', async ({ page, guard }) => {
    guard.allowStatus((url, status) => status === 401 && url.endsWith('/api/auth/me'))
    const account = newAccount('mobile-login')
    await registerViaApi(page, account)
    await page.context().clearCookies()
    await page.goto('/')
    await page.getByLabel('Email address').fill(account.email)
    await fillSecret(page.getByLabel('Password'), account.password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
  })
})
