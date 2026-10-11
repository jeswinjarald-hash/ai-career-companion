import { mkdirSync } from 'node:fs'
import path from 'node:path'
import type { Page } from '@playwright/test'
import { API_URL, expect, newAccount, registerViaApi, settleAnimations, test } from './support/fixtures'
import { SYNTHETIC_RESUMES, holdRequests, jobMatches, processResumeViaApi } from './support/resumes'
import { graphSkills, selectVisibleSkills } from '../src/lib/skillGraphData'
import { MAX_LINK_ALPHA, SCENE_PARAMS, TRANSITION_MS } from '../src/lib/skillGraphScene'
import { DEFAULT_GRAPH_CONFIG } from '../src/lib/skillGraphPhysics'
import { OCCLUDER_SELECTOR, PARALLAX } from '../src/components/skillGraphEngine'
import { snapshot, type Snapshot } from './support/skillGraph'

// Route-aware behaviour of the skill graph (Phase 6) on the isolated backend with synthetic
// resumes. Every state here is real: request-pending states are produced by holding the real
// request (holdRequests continues it to the backend), gaps come from a real skill-gap
// analysis, profile skills are saved through the real profile API for a synthetic account.
// Positions are read from the engine's read-only dev snapshot. Screenshots: e2e/.tmp/screens.
const SCREENS = path.resolve('e2e/.tmp/screens')
test.beforeAll(() => mkdirSync(SCREENS, { recursive: true }))

const canvas = (page: Page) => page.locator('canvas.skill-graph')
const sidebar = (page: Page, label: string) => page.getByRole('complementary', { name: 'Sidebar' }).getByRole('button', { name: label, exact: true })

const instrument = (page: Page) => page.addInitScript(() => {
  const w = window as unknown as { rafCalls: number; listeners: Record<string, number> }
  w.rafCalls = 0; w.listeners = {}
  const raf = window.requestAnimationFrame.bind(window)
  window.requestAnimationFrame = (callback) => { w.rafCalls++; return raf(callback) }
  const add = window.addEventListener.bind(window), remove = window.removeEventListener.bind(window)
  window.addEventListener = ((type: string, ...rest: unknown[]) => { w.listeners[type] = (w.listeners[type] ?? 0) + 1; return (add as (...a: unknown[]) => void)(type, ...rest) }) as typeof window.addEventListener
  window.removeEventListener = ((type: string, ...rest: unknown[]) => { w.listeners[type] = (w.listeners[type] ?? 0) - 1; return (remove as (...a: unknown[]) => void)(type, ...rest) }) as typeof window.removeEventListener
})
const counters = (page: Page) => page.evaluate(() => { const w = window as unknown as { rafCalls: number; listeners: Record<string, number> }; return { raf: w.rafCalls, scroll: w.listeners.scroll ?? 0, pointermove: w.listeners.pointermove ?? 0 } })

async function analysedAccount(page: Page, resume: 'backend' | 'marketing' = 'backend') {
  const profileId = await registerViaApi(page, newAccount('routes'))
  const resumeId = await processResumeViaApi(page, profileId, resume)
  const structured = await (await page.request.get(`${API_URL}/api/resumes/${resumeId}/structured`)).json() as { data: { skills: string[] } }
  const me = await (await page.request.get(`${API_URL}/api/auth/me`)).json() as { profile: { skills: string[] } }
  return { profileId, resumeId, skills: graphSkills({ resumeSkills: structured.data.skills, profileSkills: me.profile.skills }) }
}
const meanTargetError = (state: Snapshot) => {
  const pairs = state.nodes.map((node, i) => ({ node, target: state.targets?.[i] })).filter((pair) => pair.target)
  return pairs.reduce((sum, { node, target }) => sum + Math.hypot(node.x - target!.x, node.y - target!.y), 0) / Math.max(1, pairs.length)
}

test('each route sets its mode on the same engine and canvas, nodes keep their identity and positions', async ({ page }) => {
  test.setTimeout(120_000)
  await instrument(page)
  const { skills } = await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await expect(canvas(page)).toHaveAttribute('data-scene', 'overview')
  await page.evaluate(() => { (window as unknown as { firstEngine: unknown }).firstEngine = window.__skillGraph; (document.querySelector('canvas.skill-graph') as HTMLCanvasElement & { marker?: number }).marker = 1 })
  const expected = selectVisibleSkills(skills, 24)
  for (const [label, scene] of [['Resume Studio', 'resume'], ['Opportunities', 'opportunities'], ['Skill Gaps', 'skillGaps'], ['Learning Roadmap', 'skillGaps'], ['Interview Prep', 'interview'], ['Career Assistant', 'assistant'], ['Applications', 'default'], ['Profile', 'default'], ['Overview', 'overview']] as const) {
    const before = await snapshot(page)
    await sidebar(page, label).click()
    await expect(canvas(page)).toHaveAttribute('data-scene', scene)
    const after = await snapshot(page)
    // Same labels, no reset: every node continues from (close to) where it was.
    expect(after.nodes.map((node) => node.label)).toEqual(expected)
    for (const node of after.nodes) {
      const was = before.nodes.find((candidate) => candidate.label === node.label)!
      expect(Math.hypot(node.x - was.x, node.y - was.y), `${label}: ${node.label} did not jump`).toBeLessThan(80)
    }
    expect(after.scene).toBe(scene)
  }
  const same = await page.evaluate(() => (window as unknown as { firstEngine: unknown }).firstEngine === window.__skillGraph && (document.querySelector('canvas.skill-graph') as HTMLCanvasElement & { marker?: number }).marker === 1)
  expect(same, 'no engine or canvas was recreated by navigation').toBe(true)
  await expect(page.locator('canvas.skill-graph')).toHaveCount(1)
  const listeners = await counters(page)
  expect(listeners.pointermove).toBe(1)
  expect(listeners.scroll, 'one shared scroll listener for all background subsystems').toBe(1)
})

test('a route change eases into the new formation in about 1.2 s without teleporting, then sleeps', async ({ page }) => {
  test.setTimeout(120_000)
  await instrument(page)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await page.mouse.move(2, 2)
  await sidebar(page, 'Opportunities').click()
  await expect(canvas(page)).toHaveAttribute('data-scene', 'opportunities')
  // Sample the transition: progress rises, every per-sample step is bounded by the speed cap.
  const samples: Snapshot[] = []
  const start = Date.now()
  while (Date.now() - start < 1800) { samples.push(await snapshot(page)); await page.waitForTimeout(60) }
  const progress = samples.map((sample) => sample.transition).filter((value): value is number => value !== null)
  expect(progress.length, 'transition observed in progress').toBeGreaterThan(3)
  for (let i = 1; i < progress.length; i++) expect(progress[i]).toBeGreaterThanOrEqual(progress[i - 1])
  expect(samples.at(-1)!.transition, `finished within ~${TRANSITION_MS} ms (+ sampling slack)`).toBeNull()
  const mid = samples.find((sample) => (sample.transition ?? 0) > 0.35 && (sample.transition ?? 0) < 0.65)
  if (mid) await page.screenshot({ path: path.join(SCREENS, 'route-transition-mid.png') })
  for (let i = 1; i < samples.length; i++) {
    for (const node of samples[i].nodes) {
      const was = samples[i - 1].nodes.find((candidate) => candidate.label === node.label)!
      // ≤ max speed × wall-clock gap between samples (generous: evaluate latency varies).
      expect(Math.hypot(node.x - was.x, node.y - was.y)).toBeLessThan(DEFAULT_GRAPH_CONFIG.maxSpeed * 0.4)
    }
  }
  await expect.poll(async () => meanTargetError(await snapshot(page)), { timeout: 15_000 }).toBeLessThan(45)
  const settled = await snapshot(page)
  expect(settled.params).toEqual(SCENE_PARAMS.opportunities)
  for (const node of settled.nodes) {
    expect(node.x - node.w / 2).toBeGreaterThanOrEqual(-0.5)
    expect(node.x + node.w / 2).toBeLessThanOrEqual(settled.bounds.width + 0.5)
    expect(node.y - node.h / 2).toBeGreaterThanOrEqual(-0.5)
    expect(node.y + node.h / 2).toBeLessThanOrEqual(settled.bounds.height + 0.5)
  }
  await expect(canvas(page), 'formation settles and the loop sleeps').toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
  const idleAt = (await counters(page)).raf
  await page.waitForTimeout(1000)
  expect((await counters(page)).raf - idleAt).toBe(0)
})

test('rapid navigation retargets from the current state without resets or jumps', async ({ page }) => {
  test.setTimeout(120_000)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-state', 'animated')
  await page.mouse.move(2, 2)
  let previous = await snapshot(page)
  for (const label of ['Resume Studio', 'Opportunities', 'Career Assistant', 'Interview Prep', 'Overview', 'Skill Gaps']) {
    await sidebar(page, label).click()
    await page.waitForTimeout(250)                                        // well inside the 1.2 s transition
    const now = await snapshot(page)
    expect(now.transition, `${label}: a fresh transition started from the current state`).not.toBeNull()
    expect(now.transition!).toBeLessThan(0.6)
    for (const node of now.nodes) {
      const was = previous.nodes.find((candidate) => candidate.label === node.label)!
      expect(Math.hypot(node.x - was.x, node.y - was.y), `${label}: ${node.label}`).toBeLessThan(DEFAULT_GRAPH_CONFIG.maxSpeed * 0.6)
      expect(Number.isFinite(node.x) && Number.isFinite(node.y)).toBe(true)
    }
    previous = now
  }
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
})

test('constellation lines are sparse, bounded, fade with distance and appear only in open background', async ({ page }) => {
  test.setTimeout(120_000)
  await analysedAccount(page)
  await page.goto('/careers')
  await expect(page.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 })
  await page.mouse.move(2, 2)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
  const state = await snapshot(page)
  expect(state.edges.length, 'the opportunities formation links nearby skills').toBeGreaterThan(0)
  const degree = new Map<string, number>()
  const keys = new Set<string>()
  for (const edge of state.edges) {
    expect(edge.alpha).toBeLessThanOrEqual(MAX_LINK_ALPHA)
    expect(edge.alpha).toBeGreaterThan(0)
    expect(edge.distance!).toBeLessThan(state.params.linkRadius)
    const key = [edge.a, edge.b].sort().join('|')
    expect(keys.has(key), 'no undirected edge twice').toBe(false)
    keys.add(key)
    for (const end of [edge.a, edge.b]) degree.set(end, (degree.get(end) ?? 0) + 1)
  }
  for (const count of degree.values()) expect(count).toBeLessThanOrEqual(state.params.linksPerNode)
  // Closer pairs are at least as opaque as farther ones (distance fade).
  const sorted = [...state.edges].sort((a, b) => a.distance! - b.distance!)
  expect(sorted[0].alpha).toBeGreaterThanOrEqual(sorted.at(-1)!.alpha - 1e-9)
  // Drawn lines: every selected edge except pairs so close that nothing is left between the
  // two capsule outlines once the line is trimmed to them.
  const drawn = Number(await canvas(page).getAttribute('data-edge-count'))
  expect(drawn).toBeGreaterThan(0)
  expect(drawn).toBeLessThanOrEqual(state.edges.length)
  // Pixels: midpoints of lines that cross a foreground surface (away from any capsule) are
  // empty there; midpoints in open background are drawn.
  const probe = await page.evaluate((selector) => {
    const graph = window.__skillGraph!.snapshot()
    const pixels = document.querySelector<HTMLCanvasElement>('canvas.skill-graph')!.getContext('2d')!
    const boxes = Array.from(document.querySelectorAll<HTMLElement>(selector)).filter((el) => !el.parentElement?.closest(selector)).map((el) => el.getBoundingClientRect())
    const byLabel = new Map(graph.nodes.map((n) => [n.label, n]))
    return graph.edges.map((edge) => {
      const a = byLabel.get(edge.a)!, b = byLabel.get(edge.b)!
      const x = (a.x + b.x) / 2, y = (a.y + b.y) / 2 + graph.parallax
      const nearCapsule = graph.nodes.some((n) => Math.abs(n.x - x) < n.w / 2 + 8 && Math.abs(n.y + graph.parallax - y) < n.h / 2 + 8)
      const covered = boxes.some((r) => x > r.left + 2 && x < r.right - 2 && y > r.top + 2 && y < r.bottom - 2)
      const open = !boxes.some((r) => x > r.left - 3 && x < r.right + 3 && y > r.top - 3 && y < r.bottom + 3)
      const data = pixels.getImageData(Math.round(x * graph.dpr) - 1, Math.round(y * graph.dpr) - 1, 3, 3).data
      let max = 0; for (let i = 3; i < data.length; i += 4) max = Math.max(max, data[i])
      return { covered, open, nearCapsule, alpha: max, lineAlpha: edge.alpha }
    })
  }, OCCLUDER_SELECTOR)
  for (const line of probe.filter((entry) => entry.covered && !entry.nearCapsule)) expect(line.alpha, 'no line pixels behind a foreground surface').toBe(0)
  for (const line of probe.filter((entry) => entry.open && entry.lineAlpha > 0.03)) expect(line.alpha, 'lines are drawn in open background').toBeGreaterThan(0)
  await page.screenshot({ path: path.join(SCREENS, 'route-opportunities-constellation.png') })
})

test('Skill Gaps accents only the gaps a real analysis reports; without analysis nothing is added', async ({ page }) => {
  test.setTimeout(180_000)
  const { resumeId, skills } = await analysedAccount(page)
  await page.goto('/skills')                                                // no job selected: no analysis
  await expect(canvas(page)).toHaveAttribute('data-scene', 'skillGaps')
  await expect.poll(async () => (await snapshot(page)).nodes.map((node) => node.label)).toEqual(selectVisibleSkills(skills, 24))
  let state = await snapshot(page)
  expect(state.nodes.every((node) => !node.gap)).toBe(true)

  const [top] = await jobMatches(page, resumeId, 1)
  const analysisResponse = page.waitForResponse((response) => response.url().includes('/skill-gap') && response.request().method() === 'POST' && response.ok(), { timeout: 120_000 })
  await page.goto(`/skills?job=${encodeURIComponent(top.job_id)}`)
  const analysis = await (await analysisResponse).json() as { critical_gaps: Array<{ requirement: string; requirement_type: string; match_type: string }>; partial_gaps: Array<{ requirement: string; requirement_type: string; match_type: string }>; preferred_gaps: Array<{ requirement: string; requirement_type: string; match_type: string }> }
  const { gapSkillsFromAnalysis, sceneLabels } = await import('../src/lib/skillGraphData')
  const expected = sceneLabels(skills, gapSkillsFromAnalysis(analysis), 24)
  await expect.poll(async () => (await snapshot(page)).nodes.map((node) => ({ label: node.label, gap: node.gap }))).toEqual(expected)
  state = await snapshot(page)
  const reported = new Set(gapSkillsFromAnalysis(analysis).map((label) => label.toLowerCase()))
  for (const node of state.nodes.filter((entry) => entry.gap)) expect(reported.has(node.label.toLowerCase()), `${node.label} is a reported gap`).toBe(true)
  await page.mouse.move(2, 2)
  await settleAnimations(page)
  await page.waitForTimeout(1600)
  await page.screenshot({ path: path.join(SCREENS, `route-skill-gaps${expected.some((entry) => entry.gap) ? '' : '-no-skill-gaps-reported'}.png`) })

  // Leaving the screen clears the gap accents (no stale gap data elsewhere).
  await sidebar(page, 'Overview').click()
  await expect.poll(async () => (await snapshot(page)).nodes.some((node) => node.gap)).toBe(false)
  await expect.poll(async () => (await snapshot(page)).nodes.map((node) => node.label)).toEqual(selectVisibleSkills(skills, 24))
})

test('Career Assistant emphasis follows the real pending request only', async ({ page }) => {
  test.setTimeout(120_000)
  await analysedAccount(page)
  await page.goto('/assistant')
  await expect(page.getByText('Ask me anything about your career search.')).toBeVisible()
  await expect(canvas(page)).toHaveAttribute('data-scene', 'assistant')
  await page.mouse.move(2, 2)
  await expect.poll(async () => (await snapshot(page)).transition, { timeout: 5000 }).toBeNull()
  expect((await snapshot(page)).params).toEqual(SCENE_PARAMS.assistant)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
  await page.screenshot({ path: path.join(SCREENS, 'route-assistant-idle.png') })

  const held = await holdRequests(page, '**/api/career-assistant/conversations/*/messages')
  await page.getByRole('textbox', { name: 'Ask the career assistant' }).fill('What should I focus on next?')
  await page.getByRole('textbox', { name: 'Ask the career assistant' }).press('Enter')
  await expect.poll(held.count).toBe(1)
  await expect.poll(async () => (await snapshot(page)).params.linksPerNode).toBe(SCENE_PARAMS.assistant.linksPerNode + 1)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'running')        // the ring turns while pending
  await page.waitForTimeout(1300)
  await page.screenshot({ path: path.join(SCREENS, 'route-assistant-pending.png') })
  await held.release()
  await expect(page.locator('.message.assistant').first()).toBeVisible({ timeout: 60_000 })
  await expect.poll(async () => (await snapshot(page)).params, { timeout: 5000 }).toEqual(SCENE_PARAMS.assistant)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
})

test('Resume Studio clusters; the busy emphasis appears only while a real analysis runs', async ({ page }) => {
  test.setTimeout(180_000)
  const { profileId } = await analysedAccount(page)
  // Profile skills the (synthetic) user saved themselves stay visible while a replacement
  // resume is analysed — the resume's own skills are withheld until it is processed.
  const saved = await page.request.patch(`${API_URL}/api/profiles/${profileId}`, { data: { skills: ['Python', 'SQL', 'Git', 'Docker', 'Linux'] } })
  expect(saved.status()).toBe(200)
  await page.goto('/resume')
  await expect(page.getByText('Active resume · analysed')).toBeVisible()
  await expect(canvas(page)).toHaveAttribute('data-scene', 'resume')
  await page.mouse.move(2, 2)
  await expect.poll(async () => (await snapshot(page)).transition, { timeout: 5000 }).toBeNull()
  expect((await snapshot(page)).params).toEqual(SCENE_PARAMS.resume)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
  await page.screenshot({ path: path.join(SCREENS, 'route-resume-idle.png') })

  await page.locator('input[type="file"]').setInputFiles(SYNTHETIC_RESUMES.marketing)
  const slow = await holdRequests(page, '**/api/resumes/*/structure')
  await page.getByRole('button', { name: 'Upload and analyse new resume' }).click()
  await expect.poll(slow.count).toBe(1)
  await expect.poll(async () => (await snapshot(page)).params.linksPerNode).toBe(SCENE_PARAMS.resume.linksPerNode + 1)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'running')
  await page.mouse.move(2, 2)
  await page.waitForTimeout(1300)
  await page.screenshot({ path: path.join(SCREENS, 'route-resume-processing.png') })
  await slow.release()
  await expect(page).toHaveURL(/\/resume\/results$/, { timeout: 120_000 })
  await expect.poll(async () => (await snapshot(page)).params, { timeout: 5000 }).toEqual(SCENE_PARAMS.resume)
})

test('hovering an interactive opportunity card attracts gently and releases; plain cards do not', async ({ page }) => {
  test.setTimeout(120_000)
  await analysedAccount(page)
  await page.goto('/careers')
  const card = page.locator('.career-card[data-graph-magnet]').first()
  await expect(card).toBeVisible({ timeout: 60_000 })
  const plain = page.locator('.card:not([data-graph-magnet])').first()
  const plainBox = (await plain.boundingBox())!
  await page.mouse.move(plainBox.x + 20, plainBox.y + 20)
  await page.waitForTimeout(400)
  expect((await snapshot(page)).magnetWeight).toBe(0)
  await card.scrollIntoViewIfNeeded()
  const box = (await card.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 4 })
  await expect.poll(async () => (await snapshot(page)).magnetWeight).toBeGreaterThan(0.5)
  expect((await snapshot(page)).magnetWeight).toBeLessThanOrEqual(1)
  await page.screenshot({ path: path.join(SCREENS, 'route-opportunities-magnet.png') })
  await page.evaluate(() => window.dispatchEvent(new PointerEvent('pointerout', { pointerType: 'mouse', relatedTarget: null, bubbles: true })))
  await expect.poll(async () => (await snapshot(page)).magnetWeight).toBe(0)
  // The card's own controls still work under the pointer.
  await card.getByRole('button', { name: 'View details →' }).click()
  await expect(page).toHaveURL(/\/jobs\//)
})

test('scroll parallax is small, bounded, eased and leaves the content where it is', async ({ page }) => {
  test.setTimeout(120_000)
  await page.setViewportSize({ width: 1280, height: 600 })
  await analysedAccount(page)
  await page.goto('/careers')
  await expect(page.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 })
  await page.mouse.move(2, 2)
  expect((await snapshot(page)).parallax).toBe(0)
  const heading = page.locator('#main-content h1')
  await page.evaluate(() => window.scrollTo(0, 400))
  const headingTop = (await heading.boundingBox())!.y
  await expect.poll(async () => (await snapshot(page)).parallax).toBeCloseTo(-Math.min(PARALLAX.max, 400 * PARALLAX.factor), 1)
  expect((await heading.boundingBox())!.y, 'foreground content does not move with the graph').toBeCloseTo(headingTop, 0)
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await expect.poll(async () => (await snapshot(page)).parallax).toBeGreaterThanOrEqual(-PARALLAX.max - 1e-6)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0)
  await page.screenshot({ path: path.join(SCREENS, 'route-opportunities-scrolled.png') })
  await page.evaluate(() => window.scrollTo(0, 0))
  await expect.poll(async () => (await snapshot(page)).parallax).toBe(0)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
})

test('a hidden tab schedules nothing for route changes and resumes on return', async ({ page }) => {
  await instrument(page)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(canvas(page)).toHaveAttribute('data-loop', 'running')
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange')) })
  await expect(canvas(page)).toHaveAttribute('data-loop', 'paused')
  await page.waitForTimeout(100)
  const pausedAt = (await counters(page)).raf
  // Keyboard activation: a hidden tab receives no pointer input (a mouse click would
  // legitimately animate the pointer spotlight, which is not what is measured here).
  await sidebar(page, 'Opportunities').press('Enter')
  await expect(canvas(page)).toHaveAttribute('data-scene', 'opportunities')
  await sidebar(page, 'Career Assistant').press('Enter')
  await expect(canvas(page)).toHaveAttribute('data-scene', 'assistant')
  await page.waitForTimeout(600)
  expect((await counters(page)).raf - pausedAt, 'no frames while hidden').toBe(0)
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')) })
  await expect(canvas(page)).toHaveAttribute('data-loop', 'running')
  await expect.poll(async () => (await snapshot(page)).transition, { timeout: 5000 }).toBeNull()
})

test('sign-out from a skill-gap screen clears the graph, and the next user never sees the previous skills', async ({ page }) => {
  test.setTimeout(180_000)
  const first = await analysedAccount(page, 'backend')
  await page.goto('/skills')
  await expect(canvas(page)).toHaveAttribute('data-node-count', String(Math.min(24, first.skills.length)))
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(canvas(page)).toHaveAttribute('data-node-count', '0')
  await expect(canvas(page)).toHaveAttribute('data-scene', 'default')
  expect((await snapshot(page)).nodes).toEqual([])
  await registerViaApi(page, newAccount('routes-next'))                     // a different user, no resume yet
  await page.goto('/skills')
  await expect(page.locator('#main-content h1')).toBeVisible()
  await expect(canvas(page)).toHaveAttribute('data-node-count', '0')
  await page.waitForTimeout(500)
  expect((await snapshot(page)).nodes).toEqual([])
})

test.describe('reduced motion', () => {
  test.use({ contextOptions: { reducedMotion: 'reduce' } })
  test('each route is a static arrangement: no loop, no interpolation, no parallax, no frames', async ({ page }) => {
    test.setTimeout(120_000)
    await instrument(page)
    await analysedAccount(page)
    await page.goto('/dashboard')
    await expect(canvas(page)).toHaveAttribute('data-state', 'static')
    for (const [label, scene] of [['Opportunities', 'opportunities'], ['Career Assistant', 'assistant'], ['Resume Studio', 'resume']] as const) {
      await sidebar(page, label).click()
      await expect(canvas(page)).toHaveAttribute('data-scene', scene)
      // The static composition is re-placed once after the page's layout settles (data
      // loaded) — a discrete update, not animation. Wait for that, then require stillness.
      await page.waitForTimeout(900)
      const state = await snapshot(page)
      expect(state.transition).toBeNull()
      expect(state.parallax).toBe(0)
      expect(state.nodes.every((node) => node.vx === 0 && node.vy === 0)).toBe(true)
      expect(meanTargetError(state)).toBeLessThan(45)                       // the route's own arrangement
      await page.waitForTimeout(400)
      expect((await snapshot(page)).nodes).toEqual(state.nodes)              // frozen
      await expect(canvas(page)).toHaveAttribute('data-loop', 'stopped')
      // Layout changes while the page loads each cost one redraw frame; once the page is
      // quiet, nothing is scheduled at all (no loop kept alive for decoration).
      const quiet = (await counters(page)).raf
      await page.waitForTimeout(600)
      expect((await counters(page)).raf - quiet, 'no frames once the page is quiet').toBe(0)
    }
    await page.evaluate(() => window.scrollTo(0, 300))
    await page.waitForTimeout(200)
    expect((await snapshot(page)).parallax).toBe(0)
    await settleAnimations(page)
    await page.screenshot({ path: path.join(SCREENS, 'route-reduced-motion-resume.png') })
  })
})

test('route screenshots at desktop and mobile widths, no overflow', async ({ page }) => {
  test.setTimeout(240_000)
  await analysedAccount(page)
  await page.goto('/dashboard')
  await expect(page.locator('.match-row').first()).toBeVisible({ timeout: 60_000 })
  for (const [label, file] of [['Overview', 'overview'], ['Interview Prep', 'interview'], ['Learning Roadmap', 'roadmap'], ['Profile', 'default-profile']] as const) {
    await sidebar(page, label).click()
    await expect(page.locator('#main-content h1')).toBeVisible()
    await page.mouse.move(2, 2)
    await expect.poll(async () => (await snapshot(page)).transition, { timeout: 5000 }).toBeNull()
    await expect(canvas(page), `${label}: settles before the screenshot`).toHaveAttribute('data-loop', 'idle', { timeout: 30_000 })
    await page.screenshot({ path: path.join(SCREENS, `route-${file}.png`) })
  }
  for (const width of [320, 375, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: width < 768 ? 812 : 900 })
    await page.goto('/careers')
    await expect(page.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 })
    await expect(canvas(page)).toHaveAttribute('data-scene', 'opportunities')
    const state = await snapshot(page)
    expect(state.nodes.length).toBeLessThanOrEqual(width < 768 ? 10 : 24)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), `${width}px: no horizontal overflow`).toBeLessThanOrEqual(0)
    await page.waitForTimeout(1500)
    await page.screenshot({ path: path.join(SCREENS, `route-opportunities-${width}.png`) })
  }
  await page.setViewportSize({ width: 375, height: 812 })
  await page.getByRole('button', { name: 'Open navigation menu' }).click()
  await expect(page.getByRole('dialog', { name: 'Navigation menu' })).toBeVisible()
  await settleAnimations(page)
  await page.waitForTimeout(400)                                            // drawer open transition
  await page.screenshot({ path: path.join(SCREENS, 'route-mobile-navigation.png') })
  await page.getByRole('dialog', { name: 'Navigation menu' }).getByRole('button', { name: 'Career Assistant', exact: true }).click()
  await expect(canvas(page)).toHaveAttribute('data-scene', 'assistant')
})

// Visual review matrix: each route at 390/768/1280/1440 px, captured once the scene has
// settled (the loop reports idle), so the screenshot shows the composition a user sees.
// Skill Gaps uses a real analysis of the top real match. Wide screens must show the graph
// (some labelled capsules in open background), never so faint that it looks broken.
test('settled route compositions at 390, 768, 1280 and 1440 px', async ({ page }) => {
  test.setTimeout(900_000)
  const { resumeId } = await analysedAccount(page)
  const [top] = await jobMatches(page, resumeId, 1)
  const routes: Array<[string, string]> = [['/dashboard', 'overview'], ['/resume', 'resume'], ['/careers', 'opportunities'], [`/skills?job=${encodeURIComponent(top.job_id)}`, 'skillGaps'], ['/interview-prep', 'interview'], ['/assistant', 'assistant']]
  const labelledAtWide: Record<string, number> = {}
  for (const width of [390, 768, 1280, 1440]) {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 })
    for (const [url, scene] of routes) {
      await page.goto(url)
      await expect(page.locator('#main-content h1')).toBeVisible()
      await expect(canvas(page)).toHaveAttribute('data-scene', scene)
      await page.mouse.move(2, 2)
      await expect(canvas(page), `${scene} @ ${width}: settles`).toHaveAttribute('data-loop', 'idle', { timeout: 45_000 })
      const state = await snapshot(page)
      expect(state.nodes.length).toBeLessThanOrEqual(width < 768 ? 10 : 24)
      expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), `${scene} @ ${width}: no overflow`).toBeLessThanOrEqual(0)
      if (width >= 1280) labelledAtWide[`${scene}@${width}`] = state.nodes.filter((node) => node.labelAlpha === 1).length
      await page.screenshot({ path: path.join(SCREENS, `review-${scene}-${width}.png`) })
    }
  }
  console.log('labelled capsules at wide widths:', JSON.stringify(labelledAtWide))
  const total = Object.values(labelledAtWide).reduce((sum, count) => sum + count, 0)
  expect(total, 'the graph is visibly present on wide screens').toBeGreaterThanOrEqual(6)
})

test('a resting pointer near capsules does not keep the loop awake (after it was genuinely active)', async ({ page }) => {
  test.setTimeout(120_000)
  await instrument(page)
  await analysedAccount(page)
  await page.goto('/interview-prep')
  await page.mouse.move(2, 2)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 45_000 })
  const node = (await snapshot(page)).nodes.find((entry) => entry.labelAlpha === 1) ?? (await snapshot(page)).nodes[0]
  await page.mouse.move(node.x - 160, node.y + 70)
  await page.mouse.move(node.x - 30, node.y + 40, { steps: 10 })        // approach: the push wakes the loop
  await expect(canvas(page), 'the loop was active').toHaveAttribute('data-loop', 'running')
  const movingAt = (await counters(page)).raf
  await page.waitForTimeout(300)
  expect((await counters(page)).raf - movingAt, 'frames are being scheduled while things move').toBeGreaterThan(3)
  // The pointer now rests within the influence radius: the scene still reaches equilibrium.
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 45_000 })
  const restingAt = (await counters(page)).raf
  await page.waitForTimeout(1000)
  expect((await counters(page)).raf - restingAt).toBe(0)
  const state = await snapshot(page)
  expect(state.nodes.every((entry) => entry.vx === 0 && entry.vy === 0), 'no residual velocity at rest').toBe(true)
})

test('scroll bursts cause bounded layout measurement (no per-event or per-frame DOM polling)', async ({ page }) => {
  test.setTimeout(120_000)
  await page.addInitScript(() => {
    const w = window as unknown as { rects: number }
    w.rects = 0
    const original = Element.prototype.getBoundingClientRect
    Element.prototype.getBoundingClientRect = function (this: Element) { w.rects++; return original.call(this) }
  })
  await page.setViewportSize({ width: 1280, height: 600 })
  await analysedAccount(page)
  await page.goto('/careers')
  await expect(page.locator('.match-badge').first()).toBeVisible({ timeout: 60_000 })
  await page.mouse.move(2, 2)
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 45_000 })
  const surfaces = (await snapshot(page)).surfaces
  const before = await page.evaluate(() => (window as unknown as { rects: number }).rects)
  const frames = await page.evaluate(async () => {
    let count = 0
    let running = true
    const tick = () => { count++; if (running) requestAnimationFrame(tick) }
    requestAnimationFrame(tick)
    for (let i = 1; i <= 60; i++) { window.scrollTo(0, i * 6); await new Promise((resolve) => setTimeout(resolve, 8)) }
    await new Promise((resolve) => setTimeout(resolve, 600))               // includes the layout-settled re-placement
    running = false
    return count
  })
  const reads = await page.evaluate(() => (window as unknown as { rects: number }).rects) - before
  // One batch of reads per drawn frame at most, plus one settle pass — never one per event.
  const occluderElements = await page.evaluate((selector) => document.querySelectorAll(selector).length, OCCLUDER_SELECTOR)
  expect(reads, `${reads} reads over ${frames} frames (${occluderElements} candidate surfaces, ${surfaces} visible)`).toBeLessThanOrEqual((frames + 2) * (occluderElements + 4))
  expect(reads).toBeLessThan(60 * (occluderElements + 4))                // fewer than one batch per scroll event
  await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 45_000 })
})

test('nothing is drawn behind keep-clear zones (drop zone, assistant composer); they stay usable', async ({ page }) => {
  test.setTimeout(120_000)
  await analysedAccount(page)
  for (const [url, selector] of [['/resume', '.drop-zone'], ['/assistant', '.assistant-input']] as const) {
    await page.goto(url)
    await page.mouse.move(2, 2)
    await expect(canvas(page)).toHaveAttribute('data-loop', 'idle', { timeout: 45_000 })
    const alpha = await page.evaluate((zone) => {
      const rect = document.querySelector(zone)!.getBoundingClientRect()
      const graph = window.__skillGraph!.snapshot()
      const data = document.querySelector<HTMLCanvasElement>('canvas.skill-graph')!.getContext('2d')!.getImageData(Math.ceil(rect.left * graph.dpr), Math.ceil(rect.top * graph.dpr), Math.floor(rect.width * graph.dpr), Math.floor(rect.height * graph.dpr)).data
      let max = 0; for (let i = 3; i < data.length; i += 4) max = Math.max(max, data[i]); return max
    }, selector)
    expect(alpha, `${selector}: no canvas pixels behind it`).toBe(0)
    const hit = await page.evaluate((zone) => { const r = document.querySelector(zone)!.getBoundingClientRect(); return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.tagName.toLowerCase() }, selector)
    expect(hit).not.toBe('canvas')
  }
  await expect(page.getByRole('textbox', { name: 'Ask the career assistant' })).toBeEditable()
})
