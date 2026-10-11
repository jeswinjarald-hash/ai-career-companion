import { expect, test } from '@playwright/test'
import { MAX_SKILL_LABEL_LENGTH, graphSkills, normalizeSkillLabel, normalizeSkills, selectVisibleSkills } from '../../src/lib/skillGraphData'
import {
  DEFAULT_GRAPH_CONFIG, collide, createNodes, pointerAcceleration, settle, step, type Bounds, type GraphNode, type Pointer,
} from '../../src/lib/skillGraphPhysics'

const bounds: Bounds = { width: 1200, height: 800 }
const measure = (label: string) => ({ w: label.length * 7 + 20, h: 26 })
const idle: Pointer = { active: false, x: 0, y: 0, speed: 0 }
const finite = (nodes: GraphNode[]) => nodes.every((node) => [node.x, node.y, node.vx, node.vy].every(Number.isFinite))
const inside = (nodes: GraphNode[], area: Bounds) => nodes.every((node) =>
  node.x - node.w / 2 >= -0.001 && node.x + node.w / 2 <= area.width + 0.001 && node.y - node.h / 2 >= -0.001 && node.y + node.h / 2 <= area.height + 0.001)

test.describe('skill label normalisation (real data only)', () => {
  test('valid skills are kept, trimmed and whitespace-collapsed', () => {
    expect(normalizeSkills(['Python', '  React  ', 'Machine   Learning'])).toEqual(['Python', 'React', 'Machine Learning'])
  })
  test('empty, malformed and non-string values are rejected', () => {
    for (const value of ['', '   ', null, undefined, 42, {}, ['SQL'], '<script>', 'a{b}', 'bell\u0007char', '—', '!!']) expect(normalizeSkillLabel(value)).toBeNull()
    expect(normalizeSkillLabel('Data\tScience')).toBe('Data Science')   // tabs are whitespace, collapsed
  })
  test('case-insensitive duplicates are removed, first spelling kept', () => {
    expect(normalizeSkills(['FastAPI', 'fastapi', 'FASTAPI', 'SQL', 'sql'])).toEqual(['FastAPI', 'SQL'])
  })
  test('labels respect the maximum length and word count', () => {
    expect(normalizeSkillLabel('x'.repeat(MAX_SKILL_LABEL_LENGTH))).not.toBeNull()
    expect(normalizeSkillLabel('x'.repeat(MAX_SKILL_LABEL_LENGTH + 1))).toBeNull()
    expect(normalizeSkillLabel('built many things with python daily')).toBeNull()
  })
  test('no data gives no skills — nothing is substituted', () => {
    expect(graphSkills({})).toEqual([])
    expect(graphSkills({ resumeSkills: [], profileSkills: [] })).toEqual([])
    expect(graphSkills({ resumeSkills: null, profileSkills: ['  '] })).toEqual([])
  })
  test('resume skills come first, then profile skills, de-duplicated', () => {
    expect(graphSkills({ resumeSkills: ['Python', 'SQL'], profileSkills: ['sql', 'Docker'] })).toEqual(['Python', 'SQL', 'Docker'])
  })
  test('the visible subset is deterministic and capped', () => {
    const skills = Array.from({ length: 40 }, (_, i) => `Skill ${i}`)
    expect(selectVisibleSkills(skills, 24)).toEqual(skills.slice(0, 24))
    expect(selectVisibleSkills(skills, 24)).toEqual(selectVisibleSkills(skills, 24))
    expect(selectVisibleSkills(['A', 'B'], 24)).toEqual(['A', 'B'])
    expect(selectVisibleSkills(skills, -3)).toEqual([])
  })
})

test.describe('physics', () => {
  test('initialisation is deterministic for identical inputs and inside the bounds', () => {
    const labels = ['Python', 'SQL', 'React', 'Docker']
    expect(createNodes(labels, measure, bounds)).toEqual(createNodes(labels, measure, bounds))
    expect(inside(createNodes(labels, measure, bounds), bounds)).toBe(true)
  })

  test('nodes stay within the bounds over a long run, including after shrinking', () => {
    const nodes = createNodes(Array.from({ length: 24 }, (_, i) => `Skill ${i}`), measure, bounds)
    for (let i = 0; i < 2000; i++) step(nodes, 1 / 30, i / 30, bounds, { active: true, x: 600, y: 400, speed: 3000 })
    expect(inside(nodes, bounds)).toBe(true)
    const small = { width: 320, height: 600 }
    for (let i = 0; i < 300; i++) step(nodes, 1 / 30, i / 30, small, idle)
    expect(inside(nodes, small)).toBe(true)
    expect(finite(nodes)).toBe(true)
  })

  test('pointer repulsion points away from the pointer and falls off with distance', () => {
    const node = createNodes(['Python'], measure, bounds)[0]
    node.x = 500; node.y = 400
    const near = pointerAcceleration(node, { active: true, x: 470, y: 400, speed: 0 }, DEFAULT_GRAPH_CONFIG)
    const far = pointerAcceleration(node, { active: true, x: 400, y: 400, speed: 0 }, DEFAULT_GRAPH_CONFIG)
    expect(near.ax).toBeGreaterThan(0)                // pointer on the left → pushed right
    expect(Math.abs(near.ay)).toBeLessThan(1e-9)
    expect(near.ax).toBeGreaterThan(far.ax)           // stronger when closer
    expect(pointerAcceleration(node, { active: true, x: 500 - DEFAULT_GRAPH_CONFIG.influenceRadius - 1, y: 400, speed: 0 }, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
    expect(pointerAcceleration(node, { active: false, x: 499, y: 400, speed: 0 }, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
  })

  test('fast pointer movement gives a stronger but capped push', () => {
    const node = createNodes(['Python'], measure, bounds)[0]
    node.x = 500; node.y = 400
    const at = (speed: number) => pointerAcceleration(node, { active: true, x: 480, y: 400, speed }, DEFAULT_GRAPH_CONFIG).ax
    expect(at(800)).toBeGreaterThan(at(0))
    expect(at(1e9)).toBeCloseTo(at(1e6), 6)                       // capped
    const falloff = (1 - 20 / DEFAULT_GRAPH_CONFIG.influenceRadius) ** 2
    expect(at(1e9)).toBeLessThanOrEqual((DEFAULT_GRAPH_CONFIG.pointerForce + DEFAULT_GRAPH_CONFIG.maxPointerBoost) * falloff + 1e-6)
    expect(Number.isFinite(at(Number.NaN))).toBe(true)
  })

  test('a pointer exactly on a node gives a finite push, never NaN', () => {
    const node = createNodes(['Python'], measure, bounds)[0]
    const push = pointerAcceleration(node, { active: true, x: node.x, y: node.y, speed: 500 }, DEFAULT_GRAPH_CONFIG)
    expect(Number.isFinite(push.ax) && Number.isFinite(push.ay)).toBe(true)
    expect(Math.hypot(push.ax, push.ay)).toBeGreaterThan(0)
  })

  test('collisions separate overlapping capsules with bounded velocity changes', () => {
    const nodes = createNodes(['Python', 'SQL'], measure, bounds)
    nodes[0].x = nodes[1].x = 600; nodes[0].y = nodes[1].y = 400
    nodes.forEach((node) => { node.vx = 0; node.vy = 0 })
    collide(nodes, 1 / 30, DEFAULT_GRAPH_CONFIG)
    const maxDv = DEFAULT_GRAPH_CONFIG.maxCollisionAccel / 30 + 1e-9
    for (const node of nodes) expect(Math.hypot(node.vx, node.vy)).toBeLessThanOrEqual(maxDv)
    for (let i = 0; i < 300; i++) step(nodes, 1 / 30, i / 30, bounds, idle, DEFAULT_GRAPH_CONFIG, false)
    const apart = Math.abs(nodes[0].x - nodes[1].x) >= (nodes[0].w + nodes[1].w) / 2 - 1 || Math.abs(nodes[0].y - nodes[1].y) >= nodes[0].h - 1
    expect(apart).toBe(true)
  })

  test('speeds are capped and the system calms down after scattering', () => {
    const nodes = createNodes(Array.from({ length: 12 }, (_, i) => `Skill ${i}`), measure, bounds)
    let fastest = 0
    for (let i = 0; i < 60; i++) fastest = Math.max(fastest, step(nodes, 1 / 30, i / 30, bounds, { active: true, x: 600, y: 400, speed: 1e6 }))
    expect(fastest).toBeLessThanOrEqual(DEFAULT_GRAPH_CONFIG.maxSpeed + 1e-6)
    let after = 0
    for (let i = 0; i < 300; i++) after = step(nodes, 1 / 30, i / 30, bounds, idle)
    expect(after).toBeLessThan(15)                 // back to gentle drift (drift alone stays well under this)
  })

  test('a large elapsed-time gap (suspended tab) is clamped and stays stable', () => {
    const nodes = createNodes(['Python', 'SQL', 'React'], measure, bounds)
    const before = nodes.map((node) => ({ x: node.x, y: node.y }))
    step(nodes, 120, 0, bounds, idle)
    nodes.forEach((node, i) => expect(Math.hypot(node.x - before[i].x, node.y - before[i].y)).toBeLessThanOrEqual(DEFAULT_GRAPH_CONFIG.maxSpeed * DEFAULT_GRAPH_CONFIG.maxDt + 3))
    expect(step(nodes, Number.NaN, 0, bounds, idle)).toBe(0)
    expect(finite(nodes)).toBe(true)
  })

  test('settle() gives a static, in-bounds, deterministic layout', () => {
    const make = () => { const nodes = createNodes(['Python', 'SQL', 'React', 'Docker', 'Git'], measure, bounds); settle(nodes, bounds); return nodes }
    const a = make(), b = make()
    expect(a).toEqual(b)
    expect(a.every((node) => node.vx === 0 && node.vy === 0)).toBe(true)
    expect(inside(a, bounds)).toBe(true)
  })
})
