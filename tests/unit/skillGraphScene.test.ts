import { expect, test } from '@playwright/test'
import { nav, type View } from '../../src/routing'
import { gapSkillsFromAnalysis, sceneLabels, selectVisibleSkills } from '../../src/lib/skillGraphData'
import {
  DEFAULT_GRAPH_CONFIG, createNodes, formationAcceleration, magnetAcceleration, step, type Bounds, type GraphNode, type Pointer,
} from '../../src/lib/skillGraphPhysics'
import {
  MAX_LINK_ALPHA, SCENE_PARAMS, assignTargets, blendParams, easeInOutCubic, edgeAlpha, formationTargets, sceneModeForView, sceneParams, selectEdges,
  DEFAULT_SCENE, type SceneMode,
} from '../../src/lib/skillGraphScene'

const bounds: Bounds = { width: 1200, height: 800 }
const measure = (label: string) => ({ w: label.length * 7 + 20, h: 26 })
const idle: Pointer = { active: false, x: 0, y: 0, speed: 0 }
const labels = Array.from({ length: 24 }, (_, i) => `Skill ${i}`)
const inside = (nodes: GraphNode[], area: Bounds) => nodes.every((node) =>
  node.x - node.w / 2 >= -0.001 && node.x + node.w / 2 <= area.width + 0.001 && node.y - node.h / 2 >= -0.001 && node.y + node.h / 2 <= area.height + 0.001)
const ALL_VIEWS: View[] = ['dashboard', 'profile', 'resume', 'resume-results', 'careers', 'job-details', 'skills', 'customize', 'interview-prep', 'roadmap', 'assistant', 'progress', 'settings', 'applications', 'application-details']
const MODES: SceneMode[] = ['overview', 'resume', 'opportunities', 'skillGaps', 'interview', 'assistant', 'default']

test.describe('route → scene mode', () => {
  test('every existing route maps to its mode', () => {
    expect(sceneModeForView('dashboard')).toBe('overview')
    for (const view of ['resume', 'resume-results'] as View[]) expect(sceneModeForView(view)).toBe('resume')
    for (const view of ['careers', 'job-details', 'customize'] as View[]) expect(sceneModeForView(view)).toBe('opportunities')
    for (const view of ['skills', 'roadmap'] as View[]) expect(sceneModeForView(view)).toBe('skillGaps')
    expect(sceneModeForView('interview-prep')).toBe('interview')
    expect(sceneModeForView('assistant')).toBe('assistant')
    for (const view of ['profile', 'progress', 'settings', 'applications', 'application-details'] as View[]) expect(sceneModeForView(view)).toBe('default')
  })
  test('signed-out screens and unknown values fall back to the neutral default', () => {
    expect(sceneModeForView(null)).toBe('default')
    expect(sceneModeForView('no-such-view' as View)).toBe('default')
  })
  test('the mapping covers exactly the routes that exist (none invented)', () => {
    for (const item of nav) expect(ALL_VIEWS).toContain(item.id)
    for (const view of ALL_VIEWS) expect(MODES).toContain(sceneModeForView(view))
  })
})

test.describe('scene parameters and transitions', () => {
  test('easing is smooth, monotonic and clamped', () => {
    expect(easeInOutCubic(0)).toBe(0)
    expect(easeInOutCubic(1)).toBe(1)
    expect(easeInOutCubic(0.5)).toBeCloseTo(0.5)
    expect(easeInOutCubic(-3)).toBe(0)
    expect(easeInOutCubic(7)).toBe(1)
    expect(easeInOutCubic(Number.NaN)).toBe(1)
    let last = 0
    for (let t = 0; t <= 1; t += 0.01) { const v = easeInOutCubic(t); expect(v).toBeGreaterThanOrEqual(last - 1e-12); last = v }
    expect(easeInOutCubic(0.02)).toBeLessThan(0.001)   // starts gently
  })
  test('parameters blend continuously between modes', () => {
    const a = SCENE_PARAMS.overview, b = SCENE_PARAMS.resume
    expect(blendParams(a, b, 0)).toEqual(a)
    expect(blendParams(a, b, 1)).toEqual(b)
    const mid = blendParams(a, b, 0.5)
    expect(mid.formation).toBeCloseTo((a.formation + b.formation) / 2)
    expect(mid.linkAlpha).toBeCloseTo((a.linkAlpha + b.linkAlpha) / 2)
  })
  test('busy emphasis only for a real in-flight request on its own screen', () => {
    expect(sceneParams({ ...DEFAULT_SCENE, mode: 'assistant' })).toBe(SCENE_PARAMS.assistant)
    expect(sceneParams({ ...DEFAULT_SCENE, mode: 'assistant', assistantPending: true }).linkAlpha).toBeGreaterThan(SCENE_PARAMS.assistant.linkAlpha)
    expect(sceneParams({ ...DEFAULT_SCENE, mode: 'overview', assistantPending: true })).toBe(SCENE_PARAMS.overview)
    expect(sceneParams({ ...DEFAULT_SCENE, mode: 'resume', resumeProcessing: true }).linkAlpha).toBeLessThanOrEqual(MAX_LINK_ALPHA)
  })
})

test.describe('formations', () => {
  const nodes = labels.map((label) => ({ ...measure(label), gap: false }))
  test('Overview and Default are a balanced spread with only a weak pull; every mode has one target per node, in bounds', () => {
    // Phase 7: the calm modes gained a balanced (jittered-grid) spread so capsules are
    // distributed rather than wherever drift left them; the pull stays weak so drift remains.
    expect(SCENE_PARAMS.overview.formation).toBeLessThanOrEqual(0.3)
    expect(SCENE_PARAMS.default.formation).toBeLessThanOrEqual(0.3)
    for (const mode of ['overview', 'default', 'resume', 'opportunities', 'skillGaps', 'interview', 'assistant'] as SceneMode[]) {
      for (const area of [bounds, { width: 320, height: 568 }, { width: 60, height: 40 }]) {
        const targets = formationTargets(mode, nodes, area, 12.5)!
        expect(targets).toHaveLength(nodes.length)
        targets.forEach((point, i) => {
          expect(Number.isFinite(point.x) && Number.isFinite(point.y)).toBe(true)
          expect(point.x - Math.min(nodes[i].w / 2, area.width / 2)).toBeGreaterThanOrEqual(-0.001)
          expect(point.x + Math.min(nodes[i].w / 2, area.width / 2)).toBeLessThanOrEqual(area.width + 0.001)
          expect(point.y - Math.min(nodes[i].h / 2, area.height / 2)).toBeGreaterThanOrEqual(-0.001)
          expect(point.y + Math.min(nodes[i].h / 2, area.height / 2)).toBeLessThanOrEqual(area.height + 0.001)
        })
      }
    }
  })
  test('formations are deterministic and empty input gives nothing', () => {
    expect(formationTargets('opportunities', nodes, bounds, 3)).toEqual(formationTargets('opportunities', nodes, bounds, 3))
    expect(formationTargets('resume', [], bounds, 0)).toBeNull()
    expect(formationTargets('resume', nodes, { width: 0, height: 0 }, 0)).toBeNull()
  })
  test('the resume cluster stays diffuse (never collapses to a point)', () => {
    const targets = formationTargets('resume', nodes, bounds, 0)!
    let closest = Infinity
    for (let i = 0; i < targets.length; i++) for (let j = i + 1; j < targets.length; j++) closest = Math.min(closest, Math.hypot(targets[i].x - targets[j].x, targets[i].y - targets[j].y))
    expect(closest).toBeGreaterThan(20)
  })
  test('skill gaps get their own group, to the right of demonstrated skills', () => {
    const mixed = nodes.map((node, i) => ({ ...node, gap: i >= 18 }))
    const targets = formationTargets('skillGaps', mixed, bounds, 0)!
    const knownMax = Math.max(...targets.slice(0, 18).map((p) => p.x)), gapMin = Math.min(...targets.slice(18).map((p) => p.x))
    expect(gapMin).toBeGreaterThan(knownMax)
  })
  test('the assistant ring turns slowly, faster only while a request is pending', () => {
    const a = formationTargets('assistant', nodes, bounds, 0)!, b = formationTargets('assistant', nodes, bounds, 1)!
    const pa = formationTargets('assistant', nodes, bounds, 1, { assistantPending: true, resumeProcessing: false })!
    const moved = Math.hypot(b[0].x - a[0].x, b[0].y - a[0].y)
    expect(moved).toBeGreaterThan(0)
    expect(moved).toBeLessThan(30)                           // ≤ ~30 px per second
    expect(Math.hypot(pa[0].x - a[0].x, pa[0].y - a[0].y)).toBeGreaterThan(moved)
  })
})

test.describe('constellation edges', () => {
  const grid = Array.from({ length: 30 }, (_, i) => ({ x: (i % 6) * 60, y: Math.floor(i / 6) * 60 }))
  test('only pairs within the radius, each undirected edge once', () => {
    const edges = selectEdges(grid, 100, 10)
    const seen = new Set<string>()
    for (const edge of edges) {
      expect(edge.a).toBeLessThan(edge.b)
      expect(edge.distance).toBeLessThan(100)
      const key = `${edge.a}-${edge.b}`
      expect(seen.has(key)).toBe(false)
      seen.add(key)
    }
    expect(edges.length).toBeGreaterThan(0)
  })
  test('per-node and total caps are respected; closest pairs are preferred', () => {
    const edges = selectEdges(grid, 200, 2, 12)
    expect(edges.length).toBeLessThanOrEqual(12)
    const degree = new Map<number, number>()
    for (const edge of edges) { degree.set(edge.a, (degree.get(edge.a) ?? 0) + 1); degree.set(edge.b, (degree.get(edge.b) ?? 0) + 1) }
    for (const count of degree.values()) expect(count).toBeLessThanOrEqual(2)
    for (let i = 1; i < edges.length; i++) expect(edges[i].distance).toBeGreaterThanOrEqual(edges[i - 1].distance)
  })
  test('strength fades smoothly to zero at the radius (no popping) and opacity is capped', () => {
    const near = selectEdges([{ x: 0, y: 0 }, { x: 10, y: 0 }], 120, 2)[0]
    const far = selectEdges([{ x: 0, y: 0 }, { x: 119, y: 0 }], 120, 2)[0]
    expect(near.strength).toBeGreaterThan(far.strength)
    expect(far.strength).toBeLessThan(0.001)
    expect(selectEdges([{ x: 0, y: 0 }, { x: 120, y: 0 }], 120, 2)).toHaveLength(0)
    for (const boost of [0, 0.5, 1, 50, Number.NaN]) for (const alpha of [0.1, 0.3, 5]) expect(edgeAlpha(1, alpha, boost)).toBeLessThanOrEqual(MAX_LINK_ALPHA)
    expect(edgeAlpha(1, 0.1, 1)).toBeGreaterThan(edgeAlpha(1, 0.1, 0))
    expect(Number.isFinite(edgeAlpha(Number.NaN, 0.2, 0))).toBe(true)
  })
  test('empty, single and degenerate inputs give no edges', () => {
    expect(selectEdges([], 120, 2)).toEqual([])
    expect(selectEdges([{ x: 1, y: 1 }], 120, 2)).toEqual([])
    expect(selectEdges(grid, 0, 2)).toEqual([])
    expect(selectEdges(grid, 120, 0)).toEqual([])
  })
})

test.describe('route and hover forces', () => {
  test('formation pull is bounded, below the pointer push, and zero without weight', () => {
    const node = createNodes(['Python'], measure, bounds)[0]
    node.x = 0; node.y = 0; node.vx = 0; node.vy = 0
    const pull = formationAcceleration(node, { x: 5000, y: 5000 }, 1, DEFAULT_GRAPH_CONFIG)
    expect(Math.hypot(pull.ax, pull.ay)).toBeLessThanOrEqual(DEFAULT_GRAPH_CONFIG.maxFormationAccel + 1e-9)
    expect(DEFAULT_GRAPH_CONFIG.maxFormationAccel).toBeLessThan(DEFAULT_GRAPH_CONFIG.pointerForce)
    expect(formationAcceleration(node, { x: 5000, y: 5000 }, 0, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
    expect(formationAcceleration(node, null, 1, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
    expect(formationAcceleration(node, { x: Number.NaN, y: 1 }, 1, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
  })
  test('every formation comes fully to rest (so the loop can sleep), in bounds, near its slots', () => {
    for (const mode of ['resume', 'opportunities', 'skillGaps', 'interview', 'assistant'] as SceneMode[]) {
      const nodes = createNodes(labels, measure, bounds)
      const slots = formationTargets(mode, nodes.map((n) => ({ w: n.w, h: n.h, gap: false })), bounds, 0)!
      const order = assignTargets(nodes, slots)
      const targets = nodes.map((_, i) => slots[order[i]])
      let fastest = 0, moved = 0
      for (let i = 0; i < 900; i++) {
        const before = nodes.map((node) => ({ x: node.x, y: node.y }))
        fastest = step(nodes, 1 / 30, i / 30, bounds, idle, DEFAULT_GRAPH_CONFIG, false, { targets, formation: 1 })
        expect(fastest).toBeLessThanOrEqual(DEFAULT_GRAPH_CONFIG.maxSpeed + 1e-9)
        moved = Math.max(...nodes.map((node, k) => Math.hypot(node.x - before[k].x, node.y - before[k].y) * 30))
      }
      expect(inside(nodes, bounds), mode).toBe(true)
      expect(fastest, mode).toBeLessThan(0.5)
      expect(moved, mode).toBeLessThan(0.5)
      const meanError = nodes.reduce((sum, node, i) => sum + Math.hypot(node.x - targets[i].x, node.y - targets[i].y), 0) / nodes.length
      expect(meanError, mode).toBeLessThan(40)                  // collisions may nudge, the formation holds
    }
  })
  test('slot assignment is a deterministic permutation that prefers nearby slots', () => {
    const nodes = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 200, y: 0 }]
    const slots = [{ x: 210, y: 0 }, { x: 5, y: 0 }, { x: 95, y: 0 }]
    expect(assignTargets(nodes, slots)).toEqual([1, 2, 0])
    expect(assignTargets(nodes, slots)).toEqual(assignTargets(nodes, slots))
    const many = createNodes(labels, measure, bounds)
    const order = assignTargets(many, formationTargets('resume', many.map((n) => ({ w: n.w, h: n.h, gap: false })), bounds, 0)!)
    expect([...order].sort((a, b) => a - b)).toEqual(labels.map((_, i) => i))
    expect(assignTargets([], [])).toEqual([])
  })
  test('assignment never sends a node through another one resting on its path (shorter-total refinement)', () => {
    // Observed on a phone: greedy matching kept FastAPI on its own slot and sent React straight
    // down through it to the slot below — a jam the physics cannot resolve.
    const nodes = [{ x: 339, y: 486 }, { x: 339, y: 662 }]            // React above FastAPI
    const slots = [{ x: 346, y: 662 }, { x: 350, y: 801 }]
    expect(assignTargets(nodes, slots)).toEqual([0, 1])               // React takes the near slot, FastAPI moves on
    // Head-on pair on one row: each takes the slot on its own side.
    expect(assignTargets([{ x: 980, y: 654 }, { x: 1051, y: 678 }], [{ x: 912, y: 678 }, { x: 1094, y: 685 }])).toEqual([0, 1])
  })
  test('positions change continuously while the target moves (no teleport), even with huge dt', () => {
    const nodes = createNodes(labels.slice(0, 8), measure, bounds)
    const targets = nodes.map(() => ({ x: 1100, y: 700 }))
    for (let i = 0; i < 60; i++) {
      const before = nodes.map((node) => ({ x: node.x, y: node.y }))
      step(nodes, i % 10 === 0 ? 30 : 1 / 30, i / 30, bounds, idle, DEFAULT_GRAPH_CONFIG, true, { targets, formation: 1 })
      nodes.forEach((node, k) => expect(Math.hypot(node.x - before[k].x, node.y - before[k].y)).toBeLessThanOrEqual(DEFAULT_GRAPH_CONFIG.maxSpeed * DEFAULT_GRAPH_CONFIG.maxDt + 4))
    }
  })
  test('the pointer still wins against the formation pull nearby', () => {
    const [node] = createNodes(['Python'], measure, bounds)
    node.x = 600; node.y = 400; node.vx = 0; node.vy = 0
    for (let i = 0; i < 20; i++) step([node], 1 / 30, i / 30, bounds, { active: true, x: 560, y: 400, speed: 0 }, DEFAULT_GRAPH_CONFIG, false, { targets: [{ x: 560, y: 400 }], formation: 1 })
    expect(node.x).toBeGreaterThan(600)                        // pushed away from the pointer, toward +x
  })
  test('card magnet is bounded, pulls toward the card ring, never into the card, and releases at weight 0', () => {
    const card = { x: 500, y: 300, w: 200, h: 120 }
    const [node] = createNodes(['React'], measure, bounds)
    node.x = 900; node.y = 360
    const pull = magnetAcceleration(node, card, 1, DEFAULT_GRAPH_CONFIG)
    expect(pull.ax).toBeLessThan(0)                            // toward the card (−x)
    expect(Math.hypot(pull.ax, pull.ay)).toBeLessThanOrEqual(DEFAULT_GRAPH_CONFIG.magnetForce + 1e-9)
    expect(magnetAcceleration(node, card, 0, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
    expect(magnetAcceleration(node, null, 1, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
    node.x = 600; node.y = 360                                 // behind the card: no force
    expect(magnetAcceleration(node, card, 1, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
    node.x = 1190; node.y = 790                                // outside the reach: no force
    expect(magnetAcceleration(node, card, 1, DEFAULT_GRAPH_CONFIG)).toEqual({ ax: 0, ay: 0 })
    // A node pulled for a long time settles at the ring, never inside the card itself.
    node.x = 900; node.y = 360; node.vx = 0; node.vy = 0
    for (let i = 0; i < 600; i++) step([node], 1 / 30, i / 30, bounds, idle, DEFAULT_GRAPH_CONFIG, false, { magnet: card, magnetWeight: 1 })
    expect(node.x - node.w / 2).toBeGreaterThanOrEqual(card.x + card.w)
  })
})

test.describe('scene labels (real data only)', () => {
  const analysis = {
    critical_gaps: [{ requirement: 'Docker', requirement_type: 'required_skill', match_type: 'missing' }, { requirement: 'Bachelor degree in Computer Science or related field', requirement_type: 'education', match_type: 'missing' }],
    partial_gaps: [{ requirement: 'SQL', requirement_type: 'required_skill', match_type: 'partial' }, { requirement: '2 years backend', requirement_type: 'experience', match_type: 'partial' }],
    preferred_gaps: [{ requirement: 'Kubernetes', requirement_type: 'preferred_skill', match_type: 'learning_only' }, { requirement: 'Go', requirement_type: 'preferred_skill', match_type: 'demonstrated' }],
  }
  test('gaps come only from skill requirements that the analysis reports as not demonstrated', () => {
    expect(gapSkillsFromAnalysis(analysis)).toEqual(['Docker', 'SQL', 'Kubernetes'])
    expect(gapSkillsFromAnalysis(null)).toEqual([])
    expect(gapSkillsFromAnalysis({ critical_gaps: [], partial_gaps: [], preferred_gaps: [] })).toEqual([])
  })
  test('without gap data the labels are exactly the visible real skills', () => {
    const skills = ['Python', 'SQL', 'React']
    expect(sceneLabels(skills, [], 24)).toEqual(selectVisibleSkills(skills, 24).map((label) => ({ label, gap: false })))
    expect(sceneLabels([], [], 24)).toEqual([])
  })
  test('gaps mark matching skills, add the rest within a third of the cap, and respect the cap', () => {
    const skills = Array.from({ length: 30 }, (_, i) => `S${i}`).concat('SQL')
    const result = sceneLabels(['Python', 'sql', ...skills], ['SQL', 'Docker', 'Kubernetes'], 9)
    expect(result.length).toBeLessThanOrEqual(9)
    expect(result.find((entry) => entry.label === 'sql')).toEqual({ label: 'sql', gap: true })
    expect(result.filter((entry) => entry.gap && entry.label !== 'sql').map((entry) => entry.label)).toEqual(['Docker', 'Kubernetes'])
    expect(sceneLabels(['Python'], ['Docker', 'Kafka', 'Go', 'Rust'], 6).filter((entry) => entry.gap)).toHaveLength(2)
  })
})
