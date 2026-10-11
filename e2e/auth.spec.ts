import { allowSignedOutCheck, expect, fillSecret, newAccount, registerViaApi, test } from './support/fixtures'

const SIGN_IN_HEADING = 'Your career context, in one place.'

test.describe('signed out', () => {
  test.beforeEach(({ guard }) => allowSignedOutCheck(guard))

  test('root shows the sign-in screen', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1, name: SIGN_IN_HEADING })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    await expect(page).toHaveTitle(/Sign in · AI Career Companion/)
  })

  test('a protected deep link asks for sign-in instead of showing data', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { level: 1, name: SIGN_IN_HEADING })).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toHaveCount(0)
  })

  test('wrong credentials show an error and stay signed out', async ({ page, guard }) => {
    guard.allowStatus((url, status) => status === 401 && url.endsWith('/api/auth/login'))
    const account = newAccount('wrongpw')
    await registerViaApi(page, account)
    await page.context().clearCookies()
    await page.goto('/')
    await page.getByLabel('Email address').fill(account.email)
    await fillSecret(page.getByLabel('Password'), `${account.password}-wrong`)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toHaveText('Email or password is incorrect.')
    await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toHaveCount(0)
  })

  test('sign up, see the empty dashboard, sign out and sign back in', async ({ page }) => {
    const account = newAccount('signup')
    await page.goto('/signup')
    await page.getByLabel('Full name').fill(account.fullName)
    await page.getByLabel('Email address').fill(account.email)
    await fillSecret(page.getByLabel('Password', { exact: true }), account.password)
    await fillSecret(page.getByLabel('Confirm password'), account.password)
    await page.getByRole('button', { name: 'Create account' }).click()

    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { level: 1, name: /^Good (morning|afternoon|evening), E2E\.$/ })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
    await expect(page.getByText('No applications tracked yet.', { exact: false })).toBeVisible()

    await page.getByRole('button', { name: 'Sign out' }).click()
    await expect(page.getByRole('heading', { level: 1, name: SIGN_IN_HEADING })).toBeVisible()

    await page.getByLabel('Email address').fill(account.email)
    await fillSecret(page.getByLabel('Password'), account.password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
  })
})
