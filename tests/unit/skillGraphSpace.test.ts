import { expect, test } from '@playwright/test'
import {
  LABEL_KEEP_CLEARANCE, LABEL_SHOW_CLEARANCE, POINTER_MAX_SPEED, buildSpaceGrid, capsuleBoundaryDistance, capsuleClearance, filterPointerSpeed,
  labelShouldShow, placeInOpenSpace, segmentHitsRect, shouldSleep, trimToCapsules, type SleepSignals, type Surface,
} from '../../src/lib/skillGraphSpace'
import { DEFAULT_GRAPH_CONFIG, createNodes, nodeId, step, type Bounds } from '../../src/lib/skillGraphPhysics'
import { EDGE_KEEP_BONUS, formationTargets, selectEdges } from '../../src/lib/skillGraphScene'

const bounds: Bounds = { width: 1200, height: 800 }
const pill = { w: 100, h: 24 }   // a = 38, r = 12

test.describe('capsule boundary (exact pill geometry)', () => {
  test('horizontal, vertical and diagonal directions hit the true outline', () => {
    expect(capsuleBoundaryDistance(pill.w, pill.h, 1, 0)).toBeCloseTo(50)          // end cap tip
    expect(capsuleBoundaryDistance(pill.w, pill.h, -1, 0)).toBeCloseTo(50)
    expect(capsuleBoundaryDistance(pill.w, pill.h, 0, 1)).toBeCloseTo(12)          // side wall
    expect(capsuleBoundaryDistance(pill.w, pill.h, 0, -3)).toBeCloseTo(12)         // direction need not be unit
    // Diagonal: the hit point lies exactly on the outline (distance r from the core segment).
    for (const angle of [0.1, 0.3, 0.7, 1.2, 2.5, 4]) {
      const ux = Math.cos(angle), uy = Math.sin(angle)
      const t = capsuleBoundaryDistance(pill.w, pill.h, ux, uy)
      const px = t * ux, py = t * uy
      const nearest = Math.max(-38, Math.min(38, px))
      expect(Math.hypot(px - nearest, py)).toBeCloseTo(12, 6)
    }
  })
  test('a circle (w = h) and degenerate input are handled', () => {
    expect(capsuleBoundaryDistance(24, 24, 1, 1)).toBeCloseTo(12)
    expect(capsuleBoundaryDistance(pill.w, pill.h, 0, 0)).toBe(12)
    expect(Number.isFinite(capsuleBoundaryDistance(pill.w, pill.h, Number.NaN, 1))).toBe(true)
  })
})

test.describe('constellation line trimming', () => {
  const a = { x: 0, y: 0, ...pill }
  test('horizontal: from end cap to end cap, with the gap', () => {
    const s = trimToCapsules(a, { x: 200, y: 0, ...pill }, 3)!
    expect(s.x0).toBeCloseTo(53); expect(s.x1).toBeCloseTo(147); expect(s.y0).toBeCloseTo(0); expect(s.y1).toBeCloseTo(0)
  })
  test('vertical: from side wall to side wall', () => {
    const s = trimToCapsules(a, { x: 0, y: 100, ...pill }, 3)!
    expect(s.y0).toBeCloseTo(15); expect(s.y1).toBeCloseTo(85)
  })
  test('diagonal: both ends lie outside both capsules, on the centre line', () => {
    const b = { x: 160, y: 90, ...pill }
    const s = trimToCapsules(a, b, 3)!
    const inside = (p: { x: number; y: number }, c: typeof a) => { const n = Math.max(-38, Math.min(38, p.x - c.x)); return Math.hypot(p.x - c.x - n, p.y - c.y) < 12 }
    for (const p of [{ x: s.x0, y: s.y0 }, { x: s.x1, y: s.y1 }]) { expect(inside(p, a)).toBe(false); expect(inside(p, b)).toBe(false) }
    expect((s.y0 - a.y) * (b.x - a.x)).toBeCloseTo((s.x0 - a.x) * (b.y - a.y), 6)   // collinear
  })
  test('short, touching, overlapping and coincident capsules give no line', () => {
    expect(trimToCapsules(a, { x: 104, y: 0, ...pill })).toBeNull()     // 4 px apart: nothing left after the gaps
    expect(trimToCapsules(a, { x: 60, y: 0, ...pill })).toBeNull()      // overlapping
    expect(trimToCapsules(a, { x: 0, y: 0, ...pill })).toBeNull()       // coincident
  })
})

test.describe('occlusion decisions', () => {
  const card: Surface = { x: 100, y: 100, w: 300, h: 200, kind: 'glass' }
  test('clearance: positive in open space, negative when overlapping, includes the viewport edge', () => {
    expect(capsuleClearance({ x: 600, y: 400, ...pill }, [card], bounds)).toBeGreaterThan(100)
    expect(capsuleClearance({ x: 380, y: 150, ...pill }, [card], bounds)).toBeLessThan(0)
    expect(capsuleClearance({ x: 460, y: 150, ...pill }, [card], bounds)).toBeCloseTo(10)    // 410 − 400
    expect(capsuleClearance({ x: 52, y: 500, ...pill }, [], bounds)).toBeCloseTo(2)          // left viewport edge
  })
  test('label hysteresis: needs room to appear, keeps it until the room is nearly gone', () => {
    expect(labelShouldShow(false, LABEL_SHOW_CLEARANCE - 0.5)).toBe(false)
    expect(labelShouldShow(false, LABEL_SHOW_CLEARANCE)).toBe(true)
    expect(labelShouldShow(true, LABEL_KEEP_CLEARANCE + 0.5)).toBe(true)
    expect(labelShouldShow(true, LABEL_KEEP_CLEARANCE - 0.5)).toBe(false)
    expect(labelShouldShow(true, -3)).toBe(false)
    // Oscillating by ±2 px around one edge does not flicker once shown.
    let showing = labelShouldShow(false, 8)
    for (const clearance of [3, 5, 2, 4, 3]) { showing = labelShouldShow(showing, clearance); expect(showing).toBe(true) }
  })
  test('a line through a surface is detected; one beside or ending before it is not', () => {
    expect(segmentHitsRect({ x0: 0, y0: 150, x1: 600, y1: 150 }, card)).toBe(true)
    expect(segmentHitsRect({ x0: 0, y0: 50, x1: 600, y1: 50 }, card)).toBe(false)
    expect(segmentHitsRect({ x0: 0, y0: 150, x1: 90, y1: 150 }, card)).toBe(false)
    expect(segmentHitsRect({ x0: 50, y0: 0, x1: 450, y1: 400 }, card)).toBe(true)
  })
})

test.describe('open-space placement', () => {
  const surfaces: Surface[] = [
    { x: 0, y: 0, w: 260, h: 800, kind: 'glass' },          // sidebar
    { x: 300, y: 200, w: 860, h: 560, kind: 'glass' },      // content card
    { x: 300, y: 80, w: 500, h: 40, kind: 'solid' },        // heading text
    { x: 420, y: 300, w: 300, h: 200, kind: 'clear' },      // drop zone
  ]
  const grid = buildSpaceGrid(bounds, surfaces)
  const sizes = Array.from({ length: 6 }, () => ({ w: 90, h: 24 }))
  test('slots behind glass move to nearby open background, never onto text, without crowding', () => {
    const slots = [{ x: 900, y: 230 }, { x: 950, y: 240 }, { x: 1000, y: 210 }, { x: 600, y: 600 }, { x: 1100, y: 150 }, { x: 320, y: 90 }]
    const placed = placeInOpenSpace(slots, sizes, grid, 220)
    for (const [i, spot] of placed.entries()) {
      if (!spot.open) continue
      expect(capsuleClearance({ ...spot, ...sizes[i] }, surfaces, bounds)).toBeGreaterThanOrEqual(0)
      for (const [j, other] of placed.entries()) if (j !== i && other.open) expect(Math.abs(spot.x - other.x) >= sizes[i].w || Math.abs(spot.y - other.y) >= sizes[i].h).toBe(true)
      expect(Math.hypot(spot.x - slots[i].x, spot.y - slots[i].y)).toBeLessThanOrEqual(220 * Math.SQRT2 + 1)
    }
    expect(placed.filter((spot) => spot.open).length).toBeGreaterThan(2)
    expect(placeInOpenSpace(slots, sizes, grid, 220)).toEqual(placed)            // deterministic
  })
  test('a slot in a keep-clear zone with no open space nearby moves out of it (glass allowed) or stays', () => {
    const [spot] = placeInOpenSpace([{ x: 570, y: 400 }], [{ w: 90, h: 24 }], grid, 160)   // 122 px gets out of the zone
    expect(spot.open).toBe(false)
    const inClear = spot.x + 45 > 420 && spot.x - 45 < 720 && spot.y + 12 > 300 && spot.y - 12 < 500
    expect(inClear).toBe(false)
    const [stay] = placeInOpenSpace([{ x: 570, y: 400 }], [{ w: 90, h: 24 }], grid, 0)
    expect(stay).toEqual({ x: 570, y: 400, open: false })
  })
})

test.describe('sleep and pointer velocity', () => {
  const quiet: SleepSignals = { driftFaded: true, maxSpeed: 0.1, maxMovement: 0.1, pointerSpeed: 0, transition: false, busy: false, fading: false, parallaxSettling: false, magnetActive: false }
  test('sleeps only when every source is quiet — a resting pointer included', () => {
    expect(shouldSleep(quiet)).toBe(true)
    expect(shouldSleep({ ...quiet, pointerSpeed: 0.5 })).toBe(true)              // resting pointer near a capsule
    expect(shouldSleep({ ...quiet, maxSpeed: 4, maxMovement: 0.01 })).toBe(true)    // jammed: velocity cancelled, not moving
    expect(shouldSleep({ ...quiet, maxSpeed: 4, maxMovement: 0.2 })).toBe(false)    // still creeping
    for (const patch of [{ driftFaded: false }, { maxSpeed: 0.6 }, { maxMovement: 2 }, { pointerSpeed: 30 }, { transition: true }, { busy: true }, { fading: true }, { parallaxSettling: true }, { magnetActive: true }] as Array<Partial<SleepSignals>>) {
      expect(shouldSleep({ ...quiet, ...patch }), JSON.stringify(patch)).toBe(false)
    }
  })
  test('pointer speed: no spike on entering, after a gap or a teleport; filtered and capped otherwise', () => {
    expect(filterPointerSpeed(0, { x: 0, y: 0, time: 0, inside: false }, { x: 900, y: 0, time: 16 })).toBe(0)   // entered the window
    expect(filterPointerSpeed(200, { x: 0, y: 0, time: 0, inside: true }, { x: 900, y: 0, time: 400 })).toBe(0)  // refocus after a gap
    const moving = filterPointerSpeed(0, { x: 0, y: 0, time: 0, inside: true }, { x: 10, y: 0, time: 16 })
    expect(moving).toBeGreaterThan(0)
    expect(moving).toBeLessThan(10 / 0.016)                                       // filtered, not the raw instant value
    expect(filterPointerSpeed(POINTER_MAX_SPEED, { x: 0, y: 0, time: 0, inside: true }, { x: 5000, y: 0, time: 8 })).toBe(POINTER_MAX_SPEED)
    expect(filterPointerSpeed(Number.NaN, { x: 0, y: 0, time: 0, inside: true }, { x: 5, y: 0, time: 16 })).toBe(0)
  })
})

test.describe('identity and stability', () => {
  test('identity, hue and depth depend on the label only, not its position in the list', () => {
    const measure = (label: string) => ({ w: label.length * 7 + 20, h: 26 })
    const first = createNodes(['Python', 'SQL', 'React'], measure, bounds)
    const second = createNodes(['Docker', 'React', 'Python', 'SQL'], measure, bounds)
    for (const node of first) {
      const same = second.find((other) => other.id === node.id)!
      expect([same.hue, same.depth, same.label]).toEqual([node.hue, node.depth, node.label])
    }
    expect(nodeId('Machine Learning')).toBe(nodeId('machine learning'))
  })
  test('organic drift stays bounded and finite over a long run (no runaway, no NaN)', () => {
    const nodes = createNodes(Array.from({ length: 24 }, (_, i) => `Skill ${i}`), (label) => ({ w: label.length * 7 + 20, h: 26 }), bounds)
    let fastest = 0
    for (let i = 0; i < 3000; i++) fastest = Math.max(fastest, step(nodes, 1 / 30, i / 30, bounds, { active: false, x: 0, y: 0, speed: 0 }, DEFAULT_GRAPH_CONFIG, true))
    expect(fastest).toBeLessThan(60)                                              // gentle drift, far below the cap
    expect(nodes.every((n) => [n.x, n.y, n.vx, n.vy].every(Number.isFinite))).toBe(true)
  })
  test('edges drawn last frame keep priority at the per-node cap (no line swapping)', () => {
    // Node 0 can link to 1 (d = 100) or 2 (d = 110); with a cap of 1 the closer one wins …
    const points = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: -110, y: 0 }]
    expect(selectEdges(points, 150, 1).map((e) => [e.a, e.b])).toEqual([[0, 1]])
    // … unless 0–2 was already drawn and is within the keep bonus.
    expect(110 * EDGE_KEEP_BONUS).toBeLessThan(100)
    expect(selectEdges(points, 150, 1, 48, (a, b) => a === 0 && b === 2).map((e) => [e.a, e.b])).toEqual([[0, 2]])
  })
  test('anchored formations keep their ring outside the anchor surface', () => {
    const anchor = { x: 400, y: 250, w: 420, h: 300 }
    const nodes = Array.from({ length: 12 }, () => ({ w: 80, h: 24, gap: false }))
    for (const mode of ['assistant', 'resume'] as const) {
      const targets = formationTargets(mode, nodes, bounds, 0, { anchor })!
      const outside = targets.filter((p) => p.x < anchor.x || p.x > anchor.x + anchor.w || p.y < anchor.y || p.y > anchor.y + anchor.h)
      expect(outside.length, mode).toBeGreaterThanOrEqual(mode === 'assistant' ? 12 : 9)
    }
  })
  test('the opportunity streams sway slowly and boundedly with time', () => {
    const nodes = Array.from({ length: 12 }, () => ({ w: 80, h: 24, gap: false }))
    const a = formationTargets('opportunities', nodes, bounds, 0)!, b = formationTargets('opportunities', nodes, bounds, 1)!
    const moved = Math.max(...a.map((p, i) => Math.hypot(b[i].x - p.x, b[i].y - p.y)))
    expect(moved).toBeGreaterThan(0)
    expect(moved).toBeLessThan(8)
    for (let t = 0; t < 60; t += 1.7) for (const [i, p] of formationTargets('opportunities', nodes, bounds, t)!.entries()) expect(Math.abs(p.x - a[i].x)).toBeLessThanOrEqual(32.001)
  })
})
