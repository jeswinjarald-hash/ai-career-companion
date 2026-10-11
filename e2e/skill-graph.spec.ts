import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { devices, type Page } from '@playwright/test'
import { API_URL, expect, newAccount, registerViaApi, settleAnimations, test } from './support/fixtures'
import { SYNTHETIC_RESUMES, holdRequests, processResumeViaApi } from './support/resumes'
import { graphSkills, selectVisibleSkills } from '../src/lib/skillGraphData'
import { OCCLUDER_SELECTOR } from '../src/components/skillGraphEngine'
import { snapshot } from './support/skillGraph'   // dev-only engine view

// The decorative skill graph (src/components/skillGraphEngine.ts) on the isolated backend
// with synthetic resumes. Node positions come from the engine's read-only dev snapshot;
// React commits are counted through a minimal DevTools hook; frames through a wrapped
// requestAnimationFrame. Screenshots go to e2e/.tmp/screens.
const SCREENS = path.resolve('e2e/.tmp/screens')
test.beforeAll(() => mkdirSync(SCREENS, { recursive: true }))

const canvas = (page: Page) => page.locator('canvas.skill-graph')

const instrument = (page: Page) => page.addInitScript(() => {
  const w = window as unknown as { rafCalls: number; commits: number; listeners: Record<string, number> }
  w.rafCalls = 0; w.commits = 0; w.listeners = {}
  const raf = window.requestAnimationFrame.bind(window)
  window.requestAnimationFrame = (callback) => { w.rafCalls++; return raf(callback) }
  const add = window.addEventListener.bind(window), remove = window.removeEventListener.bind(window)
  window.addEventListener = ((type: string, ...rest: unknown[]) => { w.listeners[type] = (w.listeners[type] ?? 0) + 1; return (add as (...a: unknown[]) => void)(type, ...rest) }) as typeof window.addEventListener
  window.removeEventListener = ((type: string, ...rest: unknown[]) => { w.listeners[type] = (w.listeners[type] ?? 0) - 1; return (remove as (...a: unknown[]) => void)(type, ...rest) }) as typeof window.removeEventListener
  // Minimal React DevTools hook: React calls onCommitFiberRoot once per commit.
  ;(window as unknown as Record<string, unknown>).__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true, isDisabled: false, renderers: new Map(), inject: () => 1, checkDCE: () => undefined,
    onCommitFiberRoot: () => { w.commits++ }, onCommitFiberUnmount: () => undefined, onPostCommitFiberRoot: () => undefined,
  }
})
const counters = (page: Page) => page.evaluate(() => { const w = window as unknown as { rafCalls: number; commits: number; listeners: Record<string, number> }; return { raf: w.rafCalls, commits: w.commits, pointermove: w.listeners.pointermove ?? 0 } })

async function analysedAccount(page: Page, resume: 'backend' | 'marketing' = 'backend') {
  const profileId = await registerViaApi(page, newAccount('graph'))
  const resumeId = await processResumeViaApi(page, profileId, resume)
  const structured = await (await page.request.get(`${API_URL}/api/resumes/${resumeId}/structured`)).json() as { data: { skills: string[] } }
  const me = await (await page.request.get(`${API_URL}/api/auth/me`)).json() as { profile: { skills: string[] } }
  return { profileId, resumeId, skills: graphSkills({ resumeSkills: structured.data.skills, profileSkills: me.profile.skills }) }
}

test('real skills only: no resume draws nothing, an analysed resume draws exactly its skills', async ({ page }) => {
  await registerViaApi(page, newAccount('graph-empty'))
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 2, name: 'No resume uploaded yet' })).toBeVisible()
  await expect(canvas(page)).toHaveAttribute('data-state', 'off')
  await expect(canvas(page)).toHaveAttribute('data-node-count', '0')
  expect((await snapshot(page))?.nodes).toEqual([])
  await settleAnimations(page)
  await page.screenshot({ path: path.join(SCREENS, 'graph-overview-no-resume.png') })

  const profileId = await processResumeViaApi(page, (await (await page.request.get(`${API_URL}/api/auth/me`)).json() as { profile: { id: number } }).profile.id)
  void profileId
  await page.reload()
  const structured = await (await page.request.get(`${API_URL}/api/profiles/${(await (await page.request.get(`${API_URL}/api/auth/me`)).json() as { profile: { id: number } }).profile.id}/resumes`)).json() as Array<{ id: number }>
  const data = await (await page.request.get(`${API_URL}/api/resumes/${structured[0].id}/structured`)).json() as { data: { skills: string[] } }
  const expected = selectVisibleSkills(graphSkills({ resumeSkills: data.data.skills }), 24)
  expect(expected.length).toBeGreaterThan(0)
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await expect(canvas(page)).toHaveAttribute('data-node-count', String(expected.length))
  expect((await snapshot(page))!.nodes.map((node) => node.label)).toEqual(expected)

  // Decorative: hidden from assistive technology, never a hit target, behind the content.
  await expect(canvas(page)).toHaveAttribute('aria-hidden', 'true')
  expect(await canvas(page).evaluate((element) => getComputedStyle(element).pointerEvents)).toBe('none')
  const hit = await page.evaluate(() => { const node = window.__skillGraph!.snapshot().nodes[0]; return document.elementFromPoint(node.x, node.y)?.tagName.toLowerCase() })
  expect(hit).not.toBe('canvas')
  await expect(page.locator('canvas')).toHaveCount(1)
})

test('replacing the resume swaps the skills without showing the old ones, and sign-out clears them', async ({ page }) => {
  test.setTimeout(180_000)
  const first = await analysedAccount(page, 'backend')
  await page.goto('/resume')
  await expect(canvas(page)).toHaveAttribute('data-node-count', String(Math.min(24, first.skills.length)))

  await page.locator('input[type="file"]').setInputFiles(SYNTHETIC_RESUMES.marketing)
  const slow = await holdRequests(page, '**/api/resumes/*/structure')
  await page.getByRole('button', { name: 'Upload and analyse new resume' }).click()
  await expect.poll(slow.count).toBe(1)
  // Mid-replacement the previous resume's skills are gone (profile has none of its own).
  await expect(canvas(page)).toHaveAttribute('data-node-count', '0')
  await slow.release()
  await expect(page).toHaveURL(/\/resume\/results$/, { timeout: 120_000 })
  const resumes = await (await page.request.get(`${API_URL}/api/profiles/${first.profileId}/resumes`)).json() as Array<{ id: number }>
  const data = await (await page.request.get(`${API_URL}/api/resumes/${resumes[0].id}/structured`)).json() as { data: { skills: string[] } }
  const expected = selectVisibleSkills(graphSkills({ resumeSkills: data.data.skills }), 24)
  await expect.poll(async () => (await snapshot(page))!.nodes.map((node) => node.label)).toEqual(expected)
  for (const old of first.skills.filter((skill) => !expected.some((label) => label.toLowerCase() === skill.toLowerCase()))) {
    expect((await snapshot(page))!.nodes.some((node) => node.label === old)).toBe(false)
  }
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(canvas(page)).toHaveAttribute('data-node-count', '0')
})

test('the pointer repels nearby capsules, fast moves scatter within the speed cap, and the scene settles', async ({ page }) => {
  test.setTimeout(120_000)
  await instrument(page)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await settleAnimations(page)
  await page.waitForTimeout(600)
  const before = (await snapshot(page))!
  // A node with room on its left, so the push direction is unambiguous.
  const target = [...before.nodes].sort((a, b) => b.x - a.x)[0]
  await page.mouse.move(target.x - 140, target.y)
  await page.mouse.move(target.x - 28, target.y, { steps: 8 })
  await page.screenshot({ path: path.join(SCREENS, 'graph-pointer-approach.png') })
  await page.waitForTimeout(500)
  const pushed = (await snapshot(page))!.nodes.find((node) => node.label === target.label)!
  expect(pushed.x).toBeGreaterThan(target.x + 4)                 // moved away from the pointer (to the right)

  // Fast sweep through the field: stronger scatter, but never above the speed cap.
  const centre = { x: before.bounds.width / 2, y: before.bounds.height / 2 }
  await page.mouse.move(centre.x - 400, centre.y)
  await page.mouse.move(centre.x + 400, centre.y, { steps: 4 })
  await page.waitForTimeout(120)
  await page.screenshot({ path: path.join(SCREENS, 'graph-pointer-scatter.png') })
  const fastest = Math.max(...(await snapshot(page))!.nodes.map((node) => Math.hypot(node.vx, node.vy)))
  expect(fastest).toBeLessThanOrEqual(220 + 1e-6)

  // Pointer leaves: the loop settles to a static scene and stops scheduling frames.
  await page.evaluate(() => window.dispatchEvent(new PointerEvent('pointerout', { pointerType: 'mouse', relatedTarget: null, bubbles: true })))
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 25_000 })
  await page.screenshot({ path: path.join(SCREENS, 'graph-settled.png') })
  const settled = (await snapshot(page))!
  for (const node of settled.nodes) {
    expect(node.x - node.w / 2).toBeGreaterThanOrEqual(-0.5)
    expect(node.x + node.w / 2).toBeLessThanOrEqual(settled.bounds.width + 0.5)
    expect(node.y - node.h / 2).toBeGreaterThanOrEqual(-0.5)
    expect(node.y + node.h / 2).toBeLessThanOrEqual(settled.bounds.height + 0.5)
  }
  const idleStart = (await counters(page)).raf
  await page.waitForTimeout(1000)
  expect((await counters(page)).raf - idleStart).toBe(0)
})

test('pointer movement causes no React commits and coalesces into one frame', async ({ page }) => {
  await instrument(page)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await settleAnimations(page)
  await page.waitForTimeout(1500)                                   // let initial data/effects commit
  const start = await counters(page)
  expect(start.commits, 'the commit counter is live (initial renders were recorded)').toBeGreaterThan(0)
  const burst = await page.evaluate(() => {
    const w = window as unknown as { rafCalls: number }
    const before = w.rafCalls
    const node = window.__skillGraph!.snapshot().nodes[0]
    for (let i = 0; i < 50; i++) window.dispatchEvent(new PointerEvent('pointermove', { pointerType: 'mouse', clientX: node.x - 60 + i, clientY: node.y, bubbles: true }))
    return w.rafCalls - before
  })
  expect(burst).toBeLessThanOrEqual(1)                              // one shared frame (0 if one was already pending)
  for (let i = 0; i < 30; i++) await page.mouse.move(300 + i * 20, 300 + (i % 5) * 10)
  await page.waitForTimeout(300)
  expect((await counters(page)).commits - start.commits).toBe(0)   // no React re-render from pointer movement
  // Control: a real state change in the app is counted, so the zero above is meaningful.
  await page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: 'Applications', exact: true }).click()
  await expect(page.locator('#main-content h1')).toBeVisible()
  expect((await counters(page)).commits - start.commits).toBeGreaterThan(0)
})

test('one pointer listener and one engine survive Strict Mode and route changes', async ({ page }) => {
  await instrument(page)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  for (const label of ['Resume Studio', 'Opportunities', 'Applications', 'Career Assistant', 'Overview']) {
    await page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: label, exact: true }).click()
    await expect(page.locator('#main-content h1')).toBeVisible()
  }
  expect((await counters(page)).pointermove).toBe(1)
  await expect(page.locator('canvas.skill-graph')).toHaveCount(1)
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
})

test('a hidden tab pauses the loop and a visible tab resumes it', async ({ page }) => {
  await instrument(page)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-loop', 'running')
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange')) })
  await expect(canvas(page)).toHaveAttribute('data-loop', 'paused')
  await page.waitForTimeout(100)
  const pausedAt = (await counters(page)).raf
  await page.waitForTimeout(800)
  expect((await counters(page)).raf - pausedAt).toBe(0)
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')) })
  await expect(canvas(page)).toHaveAttribute('data-loop', 'running')
})

test('a missing canvas context leaves the page fully working, with no graph', async ({ page }) => {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, ...args: Parameters<typeof original>) {
      return this.classList.contains('skill-graph') ? null : original.apply(this, args)
    } as typeof original
  })
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { level: 2, name: /^Resume analysed/ })).toBeVisible()
  await expect(canvas(page)).toHaveAttribute('data-state', 'off')
  await expect(canvas(page)).toHaveAttribute('data-reason', 'no-context')
  await page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: 'Opportunities', exact: true }).click()
  await expect(page.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 })
})

test('mobile width uses the smaller node cap and a capped device pixel ratio', async ({ page }) => {
  const { skills } = await analysedAccount(page)
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-node-count', String(Math.min(10, skills.length)))
  const state = (await snapshot(page))!
  expect(state.dpr).toBeLessThanOrEqual(1.5)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0)
  await settleAnimations(page)
  await page.screenshot({ path: path.join(SCREENS, 'graph-mobile-overview.png'), fullPage: true })
})

test('screenshots: skills behind Overview, a foreground card under the pointer, Resume Studio and Opportunities', async ({ page }) => {
  test.setTimeout(120_000)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await expect(page.locator('.match-row').first()).toBeVisible({ timeout: 60_000 })
  await settleAnimations(page)
  await page.mouse.move(2, 2)
  await page.screenshot({ path: path.join(SCREENS, 'graph-overview-skills.png') })
  const card = page.locator('section.module').first()
  const box = await card.boundingBox()
  await page.mouse.move(box!.x + box!.width / 2, box!.y + 90)
  await expect(card).toHaveClass(/\bis-lit\b/)
  await page.screenshot({ path: path.join(SCREENS, 'graph-pointer-over-card.png') })
  await page.goto('/resume')
  await expect(page.getByText('Active resume · analysed')).toBeVisible()
  await settleAnimations(page)
  await page.screenshot({ path: path.join(SCREENS, 'graph-resume-studio.png') })
  await page.goto('/careers')
  await expect(page.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 })
  await settleAnimations(page)
  await page.screenshot({ path: path.join(SCREENS, 'graph-opportunities.png') })
})

test.describe('reduced motion', () => {
  test.use({ contextOptions: { reducedMotion: 'reduce' } })
  test('shows a static composition of real skills with no loop and no pointer response', async ({ page }) => {
    await instrument(page)
    const { skills } = await analysedAccount(page)
    await page.goto('/dashboard')
    await expect(canvas(page)).toHaveAttribute('data-state', 'static')
    await expect(canvas(page)).toHaveAttribute('data-loop', 'stopped')
    const still = (await snapshot(page))!
    expect(still.nodes.map((node) => node.label)).toEqual(selectVisibleSkills(skills, 24))
    expect(still.nodes.every((node) => node.vx === 0 && node.vy === 0)).toBe(true)
    const node = still.nodes[0]
    await page.mouse.move(node.x - 20, node.y, { steps: 5 })
    await page.waitForTimeout(400)
    const after = (await snapshot(page))!.nodes[0]
    expect([after.x, after.y]).toEqual([node.x, node.y])
    await settleAnimations(page)
    await page.screenshot({ path: path.join(SCREENS, 'graph-reduced-motion.png') })
  })
})

test.describe('touch-only device', () => {
  const { defaultBrowserType, ...touchPhone } = devices['Pixel 7']
  void defaultBrowserType
  test.use(touchPhone)
  test('no continuous physics: a small static composition, taps unaffected', async ({ page }) => {
    const { skills } = await analysedAccount(page)
    await page.goto('/dashboard')
    await expect(canvas(page)).toHaveAttribute('data-state', 'static')
    await expect(canvas(page)).toHaveAttribute('data-node-count', String(Math.min(10, skills.length)))
    await page.getByRole('button', { name: 'Open navigation menu' }).tap()
    await page.getByRole('dialog', { name: 'Navigation menu' }).getByRole('button', { name: 'Opportunities', exact: true }).tap()
    await expect(page).toHaveURL(/\/careers$/)
    await expect(canvas(page)).toHaveAttribute('data-loop', 'stopped')
  })
})

// Behind foreground surfaces only a faint, label-free outline may be drawn (it reads as the
// capsule gliding beneath the glass); labels appear only in open background. The ghost's
// fill is 0.035 alpha, its outline 0.55 → the label strip behind content must stay below the
// label text's alpha (0.6), and well below it.
test('labels are never drawn behind foreground surfaces, only in open background', async ({ page }) => {
  test.setTimeout(120_000)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await expect(page.locator('.match-row').first()).toBeVisible({ timeout: 60_000 })
  await settleAnimations(page)
  await page.waitForTimeout(500)
  const result = await page.evaluate((selector) => {
    const graph = window.__skillGraph!.snapshot()
    const element = document.querySelector<HTMLCanvasElement>('canvas.skill-graph')!
    const pixels = element.getContext('2d')!
    const boxes = Array.from(document.querySelectorAll<HTMLElement>(selector)).filter((el) => !el.parentElement?.closest(selector)).map((el) => el.getBoundingClientRect())
    const within = (n: { x: number; y: number; w: number; h: number }, r: DOMRect) => n.x - n.w / 2 >= r.left && n.x + n.w / 2 <= r.right && n.y - n.h / 2 >= r.top && n.y + n.h / 2 <= r.bottom
    const overlaps = (n: { x: number; y: number; w: number; h: number }, r: DOMRect) => n.x + n.w / 2 > r.left && n.x - n.w / 2 < r.right && n.y + n.h / 2 > r.top && n.y - n.h / 2 < r.bottom
    // Max alpha over the capsule's central strip (the label/fill area).
    const alphaAt = (n: { x: number; y: number; w: number; h: number }) => {
      const data = pixels.getImageData(Math.round((n.x - n.w / 4) * graph.dpr), Math.round(n.y * graph.dpr), Math.max(1, Math.round((n.w / 2) * graph.dpr)), 1).data
      let max = 0; for (let i = 3; i < data.length; i += 4) max = Math.max(max, data[i]); return max
    }
    return graph.nodes.map((n) => ({ label: n.label, hidden: boxes.some((r) => within(n, r)), open: !boxes.some((r) => overlaps(n, r)), alpha: alphaAt(n) }))
  }, OCCLUDER_SELECTOR)
  const hidden = result.filter((node) => node.hidden), open = result.filter((node) => node.open)
  expect(hidden.length, 'at least one capsule is under a card in this layout').toBeGreaterThan(0)
  for (const node of hidden) expect(node.alpha, `${node.label}: no label pixels behind a card`).toBeLessThanOrEqual(Math.round(0.06 * 255))
  for (const node of open) expect(node.alpha, `${node.label} in open background must be drawn`).toBeGreaterThan(0)
})
