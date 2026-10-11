import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { devices, type Page } from '@playwright/test'
import { expect, newAccount, registerViaApi, settleAnimations, test } from './support/fixtures'
import { processResumeViaApi } from './support/resumes'

// Pointer lighting (src/components/usePointerLight.ts): behaviour, efficiency and
// non-interference. Screenshots of resting and lit states go to e2e/.tmp/screens.
const SCREENS = path.resolve('e2e/.tmp/screens')
test.beforeAll(() => mkdirSync(SCREENS, { recursive: true }))

const ambient = (page: Page) => page.locator('.ambient')
const nextFrames = (page: Page) => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
const spotTransform = (page: Page) => page.locator('.ambient-spot.primary').evaluate((element) => (element as HTMLElement).style.transform)
const pseudoOpacity = (page: Page, selector: string, pseudo: '::before' | '::after') => page.locator(selector).first().evaluate((element, which) => Number(getComputedStyle(element, which).opacity), pseudo)

test.describe('mouse / trackpad', () => {
  test('the global spotlight follows the pointer and fades out when it leaves the window', async ({ page }) => {
    await registerViaApi(page, newAccount('spot'))
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
    await expect(ambient(page)).toHaveAttribute('data-tracking', 'on')
    await expect(ambient(page)).toHaveAttribute('data-pointer', 'out')

    await page.mouse.move(600, 300)
    await nextFrames(page)
    expect(await spotTransform(page)).toBe('translate3d(600px, 300px, 0px)')
    await expect(ambient(page)).toHaveAttribute('data-pointer', 'in')
    await expect.poll(() => page.locator('.ambient-spot.primary').evaluate((element) => Number(getComputedStyle(element).opacity))).toBeGreaterThan(0.95)

    await page.mouse.move(900, 520, { steps: 6 })
    await nextFrames(page)
    expect(await spotTransform(page)).toBe('translate3d(900px, 520px, 0px)')
    // The trailing teal light converges on the pointer, then the loop stops.
    await expect.poll(() => page.locator('.ambient-spot.secondary').evaluate((element) => (element as HTMLElement).style.transform)).toMatch(/translate3d\((899\.\d+|900)px, (519\.\d+|520)px, 0px\)/)

    await page.evaluate(() => window.dispatchEvent(new PointerEvent('pointerout', { pointerType: 'mouse', relatedTarget: null, bubbles: true })))
    await expect(ambient(page)).toHaveAttribute('data-pointer', 'out')
    await expect.poll(() => page.locator('.ambient-spot.primary').evaluate((element) => Number(getComputedStyle(element).opacity))).toBeLessThan(0.05)
  })

  test('pointer bursts coalesce into one frame, and nothing is scheduled while idle', async ({ page }) => {
    await page.addInitScript(() => {
      const original = window.requestAnimationFrame.bind(window)
      ;(window as unknown as { rafCalls: number }).rafCalls = 0
      window.requestAnimationFrame = (callback) => { (window as unknown as { rafCalls: number }).rafCalls++; return original(callback) }
    })
    await registerViaApi(page, newAccount('raf'))
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
    await settleAnimations(page)
    const calls = () => page.evaluate(() => (window as unknown as { rafCalls: number }).rafCalls)

    const scheduled = await page.evaluate(() => {
      const before = (window as unknown as { rafCalls: number }).rafCalls
      for (let i = 0; i < 50; i++) window.dispatchEvent(new PointerEvent('pointermove', { pointerType: 'mouse', clientX: 400 + i, clientY: 300, bubbles: true }))
      return (window as unknown as { rafCalls: number }).rafCalls - before
    })
    expect(scheduled).toBe(1)

    await page.waitForTimeout(1500)            // trailing light converges
    const idleStart = await calls()
    await page.waitForTimeout(800)
    expect(await calls() - idleStart).toBe(0)  // no frame loop while the pointer is still
  })

  test('cards light up locally, stay clipped and unchanged in size, and keep working', async ({ page }) => {
    test.setTimeout(120_000)
    const profileId = await registerViaApi(page, newAccount('cards'))
    await processResumeViaApi(page, profileId, 'backend')
    await page.goto('/careers')
    const card = page.locator('article.career-card').first()
    await expect(card).toBeVisible({ timeout: 60_000 })
    await settleAnimations(page)
    await page.mouse.move(5, 5)
    await page.screenshot({ path: path.join(SCREENS, 'lighting-careers-rest.png') })
    const before = await card.boundingBox()

    await page.mouse.move(before!.x + 40, before!.y + 30)
    await nextFrames(page)
    await expect(card).toHaveClass(/\bis-lit\b/)
    const local = await card.evaluate((element) => ({ x: (element as HTMLElement).style.getPropertyValue('--sx'), y: (element as HTMLElement).style.getPropertyValue('--sy') }))
    // Local to the card. The 2px hover lift can finish after the last pointer frame, so the
    // vertical coordinate may lag by up to that lift; horizontal is exact.
    expect(Math.abs(parseFloat(local.x) - 40)).toBeLessThanOrEqual(1)
    expect(Math.abs(parseFloat(local.y) - 30)).toBeLessThanOrEqual(2.5)
    await expect.poll(() => pseudoOpacity(page, 'article.career-card.is-lit', '::before')).toBeGreaterThan(0.95)
    await expect.poll(() => pseudoOpacity(page, 'article.career-card.is-lit', '::after')).toBeGreaterThan(0.95)
    // Clipped: the highlight layers occupy exactly the card's box.
    const layer = await card.evaluate((element) => { const style = getComputedStyle(element, '::before'); return { position: style.position, inset: [style.top, style.right, style.bottom, style.left].join(' '), events: style.pointerEvents } })
    expect(layer).toEqual({ position: 'absolute', inset: '0px 0px 0px 0px', events: 'none' })
    await expect(page.locator('.card.is-lit')).toHaveCount(1)
    await page.screenshot({ path: path.join(SCREENS, 'lighting-careers-hover.png') })

    // Hover lift is transform-only: layout box (offset size) does not change.
    const layout = await card.evaluate((element) => [(element as HTMLElement).offsetWidth, (element as HTMLElement).offsetHeight])
    expect(layout).toEqual([Math.round(before!.width), Math.round(before!.height)])

    await page.mouse.move(5, 5)                // over the sidebar, not a card
    await nextFrames(page)
    await expect(page.locator('.card.is-lit')).toHaveCount(0)

    // Controls inside a lit card still receive their clicks.
    const title = await card.getByRole('heading', { level: 3 }).textContent()
    await card.hover()
    await card.getByRole('button', { name: 'View details →' }).click()
    await expect(page.locator('#main-content h1')).toHaveText(title ?? '')
  })

  test('only the innermost card under the pointer is lit, and the dashboard shows it', async ({ page }) => {
    test.setTimeout(120_000)
    const profileId = await registerViaApi(page, newAccount('nested'))
    await processResumeViaApi(page, profileId, 'backend')
    await page.goto('/dashboard')
    const matches = page.locator('section', { has: page.getByRole('heading', { name: 'Top matches for your resume' }) })
    await expect(matches.locator('.match-row').first()).toBeVisible({ timeout: 60_000 })
    await settleAnimations(page)
    await page.mouse.move(5, 5)
    await page.screenshot({ path: path.join(SCREENS, 'lighting-overview-rest.png') })
    const box = await matches.boundingBox()
    await page.mouse.move(box!.x + box!.width * 0.6, box!.y + 120)
    await nextFrames(page)
    await expect(matches).toHaveClass(/\bis-lit\b/)
    await expect(page.locator('.card.is-lit')).toHaveCount(1)
    await expect.poll(() => pseudoOpacity(page, '.card.is-lit', '::after')).toBeGreaterThan(0.95)
    await page.screenshot({ path: path.join(SCREENS, 'lighting-overview-hover.png') })

    await page.goto(`/resume/results`)
    const inner = page.locator('article.result-card').first()
    await expect(inner).toBeVisible()
    const innerBox = await inner.boundingBox()
    await page.mouse.move(innerBox!.x + 20, innerBox!.y + 20)
    await nextFrames(page)
    await expect(page.locator('.card.is-lit')).toHaveCount(1)
    await expect(inner).toHaveClass(/\bis-lit\b/)
  })

  test('keyboard focus inside a card gives the static border equivalent', async ({ page }) => {
    await registerViaApi(page, newAccount('kbd-card'))
    await page.goto('/dashboard')
    const banner = page.locator('.state-banner')
    await expect(banner).toBeVisible()
    await settleAnimations(page)
    await banner.getByRole('button', { name: 'Go to Resume Studio' }).focus()
    await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab')
    await expect(banner.getByRole('button', { name: 'Go to Resume Studio' })).toBeFocused()
    await expect.poll(() => pseudoOpacity(page, '.state-banner', '::after')).toBeGreaterThan(0.95)
  })

  test('switching on reduced motion mid-session stops tracking and clears lit cards', async ({ page }) => {
    await registerViaApi(page, newAccount('rm-live'))
    await page.goto('/dashboard')
    const banner = page.locator('.state-banner')
    await expect(banner).toBeVisible()
    const box = await banner.boundingBox()
    await page.mouse.move(box!.x + 30, box!.y + 30)
    await nextFrames(page)
    await expect(banner).toHaveClass(/\bis-lit\b/)
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await expect(ambient(page)).toHaveAttribute('data-tracking', 'off')
    await expect(page.locator('.card.is-lit')).toHaveCount(0)
    expect(await page.locator('.ambient-spot.primary').evaluate((element) => getComputedStyle(element).display)).toBe('none')
    await page.mouse.move(box!.x + 60, box!.y + 40)
    await nextFrames(page)
    await expect(page.locator('.card.is-lit')).toHaveCount(0)
    // Hover lift is removed too.
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
    await page.getByRole('button', { name: 'Upload resume' }).hover()
    expect(await page.getByRole('button', { name: 'Upload resume' }).evaluate((element) => getComputedStyle(element).transform)).toBe('none')
  })
})

test.describe('touch-only device', () => {
  // Touch phone emulation (viewport, touch, coarse pointer); the browser itself is the project's.
  const { defaultBrowserType, ...touchPhone } = devices['Pixel 7']
  void defaultBrowserType
  test.use(touchPhone)

  test('no pointer tracking; taps, navigation and the upload picker work normally', async ({ page }) => {
    await registerViaApi(page, newAccount('touch'))
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
    await expect(ambient(page)).toHaveAttribute('data-tracking', 'off')
    await page.locator('.state-banner').tap()
    await nextFrames(page)
    await expect(page.locator('.card.is-lit')).toHaveCount(0)
    await expect(ambient(page)).toHaveAttribute('data-pointer', 'out')
    await page.getByRole('button', { name: 'Open navigation menu' }).tap()
    await expect(page.getByRole('dialog', { name: 'Navigation menu' })).toBeVisible()
    await settleAnimations(page)
    await page.screenshot({ path: path.join(SCREENS, 'lighting-touch-drawer.png') })
    await page.getByRole('dialog', { name: 'Navigation menu' }).getByRole('button', { name: 'Resume Studio', exact: true }).tap()
    await expect(page).toHaveURL(/\/resume$/)
    await page.locator('input[type="file"]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('x') })
    await expect(page.getByRole('alert')).toHaveText('That file type is not supported. Please choose a PDF or DOCX resume.')
    await settleAnimations(page)
    await page.screenshot({ path: path.join(SCREENS, 'lighting-touch-resume.png'), fullPage: true })
  })
})
