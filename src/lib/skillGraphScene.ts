// Route-aware scene description for the decorative skill graph: which visual mode each real
// route uses, the per-mode parameters, the target formations, transition easing and the
// constellation (edge) selection. Pure TypeScript — no DOM, no React — unit-tested in
// tests/unit/skillGraphScene.test.ts. The engine (src/components/skillGraphEngine.ts) owns
// positions and the loop; this module only answers "where should node i be heading" and
// "which nearby pairs get a line".
//
// Truthfulness: formations are layouts of the user's real skills only. Edges are decorative
// proximity lines (no relationship data exists in the API contract), never presented as a
// dependency or recommendation. Gap accents come only from a real skill-gap analysis.
import type { View } from '../routing'
import type { Bounds } from './skillGraphPhysics'

export type SceneMode = 'overview' | 'resume' | 'opportunities' | 'skillGaps' | 'interview' | 'assistant' | 'default'

// Every existing route maps to a mode; there is no catch-all string matching. Signed-out
// screens (no view) use 'default', and the graph has no skills there anyway.
const MODE_FOR_VIEW: Record<View, SceneMode> = {
  'dashboard': 'overview',
  'resume': 'resume',
  'resume-results': 'resume',
  'careers': 'opportunities',
  'job-details': 'opportunities',
  'customize': 'opportunities',
  'skills': 'skillGaps',
  'roadmap': 'skillGaps',
  'interview-prep': 'interview',
  'assistant': 'assistant',
  'applications': 'default',
  'application-details': 'default',
  'profile': 'default',
  'progress': 'default',
  'settings': 'default',
}
export const sceneModeForView = (view: View | null): SceneMode => (view ? MODE_FOR_VIEW[view] ?? 'default' : 'default')

// Live, real context that can modulate a mode. All false/empty unless the app reports it.
export type SceneContext = {
  mode: SceneMode
  resumeProcessing: boolean     // a resume upload/analysis request is actually in flight
  assistantPending: boolean     // a Career Assistant message request is actually in flight
  gapSkills: readonly string[]  // skill requirements a real skill-gap analysis reported as not demonstrated
}
export const DEFAULT_SCENE: SceneContext = { mode: 'default', resumeProcessing: false, assistantPending: false, gapSkills: [] }

export type SceneParams = {
  formation: number      // 0 = free drift, 1 = full pull toward the formation targets
  drift: number          // multiplier on the ambient drift
  linkRadius: number     // constellation connection radius (px)
  linkAlpha: number      // peak line opacity (before the global cap)
  linksPerNode: number   // per-node connection cap
}
export const MAX_LINK_ALPHA = 0.42
export const SCENE_PARAMS: Record<SceneMode, SceneParams> = {
  overview:      { formation: 0.3,  drift: 1,    linkRadius: 140, linkAlpha: 0.26, linksPerNode: 2 },
  default:       { formation: 0.25, drift: 0.8,  linkRadius: 120, linkAlpha: 0.16, linksPerNode: 2 },
  resume:        { formation: 0.8,  drift: 0.7,  linkRadius: 135, linkAlpha: 0.32, linksPerNode: 3 },
  opportunities: { formation: 0.85, drift: 0.6,  linkRadius: 150, linkAlpha: 0.32, linksPerNode: 2 },
  skillGaps:     { formation: 0.9,  drift: 0.5,  linkRadius: 140, linkAlpha: 0.3,  linksPerNode: 3 },
  interview:     { formation: 0.85, drift: 0.55, linkRadius: 125, linkAlpha: 0.3,  linksPerNode: 2 },
  assistant:     { formation: 0.85, drift: 0.5,  linkRadius: 140, linkAlpha: 0.3,  linksPerNode: 2 },
}

// Real activity emphasis: slightly more connected while a real request is in flight.
export function sceneParams(context: SceneContext): SceneParams {
  const base = SCENE_PARAMS[context.mode]
  const busy = (context.mode === 'resume' && context.resumeProcessing) || (context.mode === 'assistant' && context.assistantPending)
  return busy ? { ...base, linkAlpha: Math.min(MAX_LINK_ALPHA, base.linkAlpha + 0.08), linksPerNode: base.linksPerNode + 1 } : base
}

export const TRANSITION_MS = 1200
export const easeInOutCubic = (t: number): number => {
  const x = Math.min(1, Math.max(0, Number.isFinite(t) ? t : 1))
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2
}
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
export function blendParams(a: SceneParams, b: SceneParams, t: number): SceneParams {
  return {
    formation: lerp(a.formation, b.formation, t),
    drift: lerp(a.drift, b.drift, t),
    linkRadius: lerp(a.linkRadius, b.linkRadius, t),
    linkAlpha: lerp(a.linkAlpha, b.linkAlpha, t),
    linksPerNode: t < 0.5 ? a.linksPerNode : b.linksPerNode,
  }
}

// --- formations ---------------------------------------------------------------------------
export type FormationNode = { w: number; h: number; gap: boolean }
export type Point = { x: number; y: number }

// Optional live context for a formation: real request states, and the route's main surface
// (`anchor`, measured from the page: the upload drop zone, the assistant panel) so the
// formation is laid out around it rather than on top of it.
export type FormationContext = Partial<Pick<SceneContext, 'assistantPending' | 'resumeProcessing'>> & { anchor?: { x: number; y: number; w: number; h: number } | null }

// Target point per node for a mode. Deterministic for the same inputs; `time` (s) drives
// only slow, idle-fading motion (the assistant orbit, the opportunity streams' sway). Every
// target keeps the whole capsule inside the bounds (plus a margin). Overview and Default use a
// balanced spread with only a weak pull (see SCENE_PARAMS), so their drift stays organic.
export function formationTargets(mode: SceneMode, nodes: readonly FormationNode[], bounds: Bounds, time: number, context: FormationContext = {}): Point[] | null {
  const n = nodes.length
  if (n === 0 || bounds.width <= 0 || bounds.height <= 0) return null
  const W = bounds.width, H = bounds.height, cx = W / 2, cy = H / 2
  const unit = Math.min(W, H)
  let points: Point[]
  switch (mode) {
    case 'overview':
    case 'default': {
      // Jittered grid over the field: balanced, never rigid (stable per-slot jitter).
      const cols = Math.max(1, Math.round(Math.sqrt((n * W) / H))), rows = Math.max(1, Math.ceil(n / cols))
      points = nodes.map((_, i) => {
        const col = i % cols, row = Math.floor(i / cols)
        const jx = Math.sin(i * 12.9898) * 0.28, jy = Math.cos(i * 78.233) * 0.28
        return { x: W * (0.06 + 0.88 * ((col + 0.5 + jx) / cols)), y: H * (0.12 + 0.78 * ((row + 0.5 + jy) / rows)) }
      })
      break
    }
    case 'resume': {
      // Diffuse sunflower cluster sized by the node count: even spacing, never a single point;
      // a little tighter only while a real analysis is running.
      const spacing = Math.min(SUNFLOWER_SPACING, (unit * 0.45) / Math.sqrt(n)) * (context.resumeProcessing ? 0.9 : 1)
      const anchor = context.anchor
      if (anchor && anchor.w > 0 && anchor.h > 0) {
        // An ingestion ring around the drop zone: the same spiral, pushed out past its edge.
        const centre = { x: anchor.x + anchor.w / 2, y: anchor.y + anchor.h / 2 }
        const inner = Math.hypot(anchor.w * 0.5, anchor.h * 0.5) + 24
        points = sunflower(n, { x: 0, y: 0 }, spacing).map((p) => {
          const d = Math.hypot(p.x, p.y) || 1
          return { x: centre.x + (p.x / d) * (inner + d * 0.7), y: centre.y + (p.y / d) * (inner * 0.75 + d * 0.5) }
        })
      } else points = sunflower(n, { x: cx, y: cy }, spacing)
      break
    }
    case 'opportunities': {
      // Up to three broad staggered bands ("streams"); neighbours in a band sit about one
      // link apart, so each stream reads as connected, and the band is centred.
      const bands = n < 6 ? Math.max(1, Math.min(2, n)) : 3
      points = nodes.map((_, i) => {
        const band = i % bands, inBand = Math.floor(i / bands), perBand = Math.ceil((n - band) / bands)
        const span = Math.min(W * 0.84, perBand * STREAM_SPACING)
        const x = cx - span / 2 + span * ((inBand + 0.5 + (band % 2) * 0.3) / Math.max(1, perBand))
        const y = H * (bands === 1 ? 0.5 : 0.26 + (0.48 * band) / (bands - 1)) + (inBand % 2 ? 12 : -12)
        // Each stream sways slowly along its direction (alternating), fading with the idle drift.
        const sway = 16 * Math.sin(time * 0.22 + band * 1.7) * (band % 2 ? -1 : 1)
        return { x: x + sway, y }
      })
      break
    }
    case 'skillGaps': {
      // Structured lattice: demonstrated skills on the left of the field, real gaps in a
      // separate group on the right. Cells are bounded so neighbours stay linkable.
      const known = nodes.map((node, i) => ({ node, i })).filter((entry) => !entry.node.gap)
      const gaps = nodes.map((node, i) => ({ node, i })).filter((entry) => entry.node.gap)
      points = new Array<Point>(n)
      const lattice = (entries: typeof known, x0: number, x1: number) => {
        if (entries.length === 0) return
        const cols = Math.max(1, Math.min(entries.length, Math.round(Math.sqrt(entries.length * ((x1 - x0) / H) * 0.6))))
        const rows = Math.max(1, Math.ceil(entries.length / cols))
        const cellW = Math.min((x1 - x0) / cols, LATTICE_CELL.w), cellH = Math.min((H * 0.7) / rows, LATTICE_CELL.h)
        const left = (x0 + x1) / 2 - (cols * cellW) / 2, top = cy - (rows * cellH) / 2
        entries.forEach(({ i }, k) => {
          const col = k % cols, row = Math.floor(k / cols)
          points[i] = { x: left + cellW * (col + 0.5 + (row % 2) * 0.22), y: top + cellH * (row + 0.5) }
        })
      }
      if (gaps.length) { lattice(known, W * 0.08, W * 0.64); lattice(gaps, W * 0.68, W * 0.94) } else lattice(known, W * 0.1, W * 0.9)
      break
    }
    case 'interview': {
      // A central cluster (about half the nodes) with two smaller satellite groups.
      const main = Math.ceil(n / 2), first = Math.ceil((n - main) / 2), second = n - main - first
      const spacing = Math.min(SUNFLOWER_SPACING * 0.9, (unit * 0.32) / Math.sqrt(main))
      points = [
        ...sunflower(main, { x: cx, y: cy }, spacing),
        ...sunflower(first, { x: W * 0.2, y: H * 0.26 }, spacing),
        ...sunflower(second, { x: W * 0.8, y: H * 0.74 }, spacing),
      ]
      break
    }
    case 'assistant': {
      // Stable angles on an ellipse sized by the node count (neighbours about one link apart);
      // the whole ring turns very slowly — faster and slightly tighter only while a real
      // request is pending.
      const turn = time * (context.assistantPending ? 0.12 : 0.035)
      const tighten = context.assistantPending ? 0.94 : 1
      const anchor = context.anchor
      // Around the real assistant panel when it is measured (the ring passes just outside its
      // edges, so the conversation and composer stay clear); otherwise sized by node count.
      const centre = anchor && anchor.w > 0 ? { x: anchor.x + anchor.w / 2, y: anchor.y + anchor.h / 2 } : { x: cx, y: cy }
      const rx = (anchor && anchor.w > 0 ? anchor.w / 2 + 70 : Math.min(W * 0.4, Math.max(150, (n * ORBIT_SPACING) / (2 * Math.PI) * 1.25))) * tighten
      const ry = (anchor && anchor.h > 0 ? anchor.h / 2 + 50 : Math.min(H * 0.38, rx * 0.62)) * tighten
      points = nodes.map((_, i) => {
        const a = (i / n) * Math.PI * 2 + turn
        return { x: centre.x + Math.cos(a) * rx, y: centre.y + Math.sin(a) * ry }
      })
      break
    }
  }
  return points.map((point, i) => clampTarget(point, nodes[i], bounds))
}

// Golden-angle spiral, stretched horizontally because capsules are wider than tall.
// `spacing` is roughly the distance between neighbouring points (px).
const SUNFLOWER_SPACING = 56
const STREAM_SPACING = 130                    // px between neighbours in an opportunities band
const LATTICE_CELL = { w: 150, h: 92 }       // skill-gap lattice cell bounds (px)
const ORBIT_SPACING = 120                     // px of ring per node on the assistant orbit
function sunflower(count: number, centre: Point, spacing: number): Point[] {
  return Array.from({ length: count }, (_, k) => {
    const r = spacing * Math.sqrt(k + 0.5), a = k * 2.399963
    return { x: centre.x + Math.cos(a) * r * 1.45, y: centre.y + Math.sin(a) * r * 0.8 }
  })
}

const TARGET_MARGIN = 16
function clampTarget(point: Point, node: FormationNode, bounds: Bounds): Point {
  const halfW = Math.min(node.w / 2 + TARGET_MARGIN, bounds.width / 2), halfH = Math.min(node.h / 2 + TARGET_MARGIN, bounds.height / 2)
  const x = Number.isFinite(point.x) ? point.x : bounds.width / 2, y = Number.isFinite(point.y) ? point.y : bounds.height / 2
  return { x: Math.min(bounds.width - halfW, Math.max(halfW, x)), y: Math.min(bounds.height - halfH, Math.max(halfH, y)) }
}

// --- constellation edges -------------------------------------------------------------------
export type Edge = { a: number; b: number; distance: number; strength: number }

// Nearby pairs (i < j, so no undirected edge twice), closest first, at most `perNode` per
// node and `maxEdges` overall. `strength` is 1 at contact and falls smoothly to 0 at the
// radius (smoothstep), so a line fades out instead of popping at the threshold.
// `kept(i, j)` marks edges drawn last frame: they rank as if 15% closer when the per-node cap
// decides, so a pair near the cap does not swap lines back and forth every frame (hysteresis).
export const EDGE_KEEP_BONUS = 0.85
export function selectEdges(points: readonly Point[], radius: number, perNode: number, maxEdges = 48, kept?: (a: number, b: number) => boolean): Edge[] {
  if (!(radius > 0) || perNode <= 0) return []
  const candidates: Array<Edge & { rank: number }> = []
  for (let i = 0; i < points.length; i++) {
    for (let j = i + 1; j < points.length; j++) {
      const distance = Math.hypot(points[j].x - points[i].x, points[j].y - points[i].y)
      if (!(distance < radius)) continue
      const x = 1 - distance / radius
      candidates.push({ a: i, b: j, distance, strength: x * x * (3 - 2 * x), rank: kept?.(i, j) ? distance * EDGE_KEEP_BONUS : distance })
    }
  }
  candidates.sort((p, q) => p.rank - q.rank || p.a - q.a || p.b - q.b)
  const degree = new Array<number>(points.length).fill(0)
  const edges: Edge[] = []
  for (const edge of candidates) {
    if (edges.length >= maxEdges) break
    if (degree[edge.a] >= perNode || degree[edge.b] >= perNode) continue
    degree[edge.a]++; degree[edge.b]++
    edges.push({ a: edge.a, b: edge.b, distance: edge.distance, strength: edge.strength })
  }
  return edges
}

// Line opacity: distance strength × mode alpha, lifted slightly near the pointer, capped.
export function edgeAlpha(strength: number, modeAlpha: number, pointerBoost: number): number {
  const value = Math.max(0, strength) * Math.max(0, modeAlpha) * (1 + 0.6 * Math.min(1, Math.max(0, pointerBoost)))
  return Math.min(MAX_LINK_ALPHA, Number.isFinite(value) ? value : 0)
}

// Which formation slot each node takes: closest pairs first (greedy over all node–slot
// distances), then refined by pairwise swaps that shorten total travel, so nodes do not cross
// the field or jam each other on the way. Computed once per transition, data/size change or
// layout settle (not per frame), so the assignment is stable. Returns slot index per node.
export function assignTargets(nodes: readonly Point[], slots: readonly Point[]): number[] {
  const pairs: Array<{ node: number; slot: number; distance: number }> = []
  for (let node = 0; node < nodes.length; node++) for (let slot = 0; slot < slots.length; slot++) pairs.push({ node, slot, distance: Math.hypot(nodes[node].x - slots[slot].x, nodes[node].y - slots[slot].y) })
  pairs.sort((a, b) => a.distance - b.distance || a.node - b.node || a.slot - b.slot)
  const result = new Array<number>(nodes.length).fill(-1)
  const taken = new Set<number>()
  for (const pair of pairs) {
    if (result[pair.node] !== -1 || taken.has(pair.slot)) continue
    result[pair.node] = pair.slot
    taken.add(pair.slot)
  }
  const order = result.map((slot, node) => (slot === -1 ? node : slot))
  // Refinement: swap two nodes' slots whenever that shortens their total travel. Greedy
  // matching can send one node straight through another's resting place (a jam the physics
  // cannot resolve); a shorter-total matching has no crossing or blocking paths of that kind.
  const travel = (node: number, slot: number) => (slots[slot] ? Math.hypot(nodes[node].x - slots[slot].x, nodes[node].y - slots[slot].y) : 0)
  for (let pass = 0; pass < 24; pass++) {
    let improved = false
    for (let i = 0; i < order.length; i++) {
      for (let j = i + 1; j < order.length; j++) {
        if (travel(i, order[j]) + travel(j, order[i]) < travel(i, order[i]) + travel(j, order[j]) - 1e-6) {
          const swap = order[i]; order[i] = order[j]; order[j] = swap
          improved = true
        }
      }
    }
    if (!improved) break
  }
  return order
}
