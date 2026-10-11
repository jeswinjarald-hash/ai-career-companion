import type { Page } from '@playwright/test'
import { expect, newAccount, registerViaApi, settleAnimations, test } from './support/fixtures'
import { processResumeViaApi } from './support/resumes'

// Interaction-quality gates for the visual system: reduced motion, visible keyboard focus,
// no continuous rendering at rest, and decorative layers that never take input.
test('reduced-motion users get no entry animations or transitions', async ({ page }) => {
  await registerViaApi(page, newAccount('motion'))
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
  const timing = await page.evaluate(() => {
    const enter = getComputedStyle(document.querySelector('.page-enter')!)
    const nav = getComputedStyle(document.querySelector('.nav-item')!)
    return { animation: enter.animationDuration, transition: nav.transitionDuration }
  })
  expect(parseFloat(timing.animation)).toBeLessThanOrEqual(0.0001)   // 0.01ms
  expect(parseFloat(timing.transition)).toBeLessThanOrEqual(0.0001)
  await page.setViewportSize({ width: 375, height: 812 })
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  expect(parseFloat(await page.evaluate(() => getComputedStyle(document.querySelector('.drawer')!).animationDuration))).toBeLessThanOrEqual(0.0001)
})

test('keyboard focus is clearly visible on navigation, buttons, fields and links', async ({ page }) => {
  await registerViaApi(page, newAccount('focus'))
  await page.goto('/profile')
  await expect(page.getByLabel('Full name')).toBeVisible()
  const focusStyle = async (locator: ReturnType<Page['locator']>) => {
    await locator.focus()
    await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab')   // keyboard modality → :focus-visible
    return locator.evaluate((element) => { const style = getComputedStyle(element); return { outline: style.outlineStyle, width: parseFloat(style.outlineWidth), shadow: style.boxShadow } })
  }
  const visible = (style: { outline: string; width: number; shadow: string }) => (style.outline !== 'none' && style.width >= 2) || style.shadow !== 'none'
  const targets = [
    page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: 'Opportunities', exact: true }),
    page.getByRole('button', { name: 'Save changes' }),
    page.getByLabel('Full name'),
    page.getByRole('button', { name: 'Sign out' }),
  ]
  for (const target of targets) expect(visible(await focusStyle(target)), await target.textContent() ?? 'field').toBe(true)
})

test('at rest only the ambient light animates — transform-only — and reduced motion stops it', async ({ page }) => {
  test.setTimeout(150_000)
  const profileId = await registerViaApi(page, newAccount('perf'))
  await processResumeViaApi(page, profileId, 'backend')
  const describe = () => page.evaluate(() => document.getAnimations().filter((animation) => animation.playState === 'running').map((animation) => {
    const effect = animation.effect as KeyframeEffect | null
    const target = effect?.target as HTMLElement | null
    const properties = [...new Set((effect?.getKeyframes() ?? []).flatMap((frame) => Object.keys(frame).filter((key) => !['offset', 'computedOffset', 'easing', 'composite'].includes(key))))]
    return { target: target?.className ?? '?', properties }
  }))
  for (const [path, ready] of [['/dashboard', '.match-row'], ['/resume/results', '.coverage-list'], ['/careers', '.match-badge']] as const) {
    await page.goto(path)
    await expect(page.locator(ready).first()).toBeVisible({ timeout: 60_000 })
    await settleAnimations(page)
    const running = await describe()
    expect(running.length, path).toBe(3)
    for (const animation of running) {
      expect(animation.target, path).toMatch(/^ambient-orb /)
      expect(animation.properties, path).toEqual(['transform'])
    }
    // Decorative: below the content and never a hit target.
    expect(await page.evaluate(() => getComputedStyle(document.querySelector('.ambient')!).pointerEvents)).toBe('none')
  }
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/dashboard')
  await expect(page.locator('.match-row').first()).toBeVisible({ timeout: 60_000 })
  await settleAnimations(page)
  expect(await describe()).toEqual([])
})

test('decorative layers never intercept input', async ({ page }) => {
  await registerViaApi(page, newAccount('layers'))
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
  // Every primary control receives its own click (nothing decorative sits on top of it).
  for (const name of ['Upload resume', 'Go to Resume Studio', 'Sign out']) {
    const control = page.getByRole('button', { name, exact: true })
    const hit = await control.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2)
      return top === element || element.contains(top)
    })
    expect(hit, name).toBe(true)
  }
  // The drawer backdrop exists only while the drawer is open, and closes it when clicked.
  await page.setViewportSize({ width: 375, height: 812 })
  await expect(page.locator('.drawer-backdrop')).toHaveCount(0)
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  await page.locator('.drawer-backdrop').click({ position: { x: 360, y: 400 } })
  await expect(page.getByRole('dialog', { name: 'Navigation menu' })).toBeHidden()
  await expect(page.locator('.drawer-backdrop')).toHaveCount(0)
})
