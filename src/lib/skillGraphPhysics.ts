// Lightweight, deterministic physics for the decorative skill graph. Pure TypeScript (no DOM,
// no React) so it is unit-tested directly (tests/unit/skillGraph.test.ts).
// Units: CSS pixels and seconds. Every force and velocity is bounded.
//
// Collision detection is all-pairs: the graph is capped at 24 nodes (276 pairs), which costs
// far less than one canvas draw call. A uniform grid would only pay off for hundreds of
// nodes; `collide` is isolated so it can be swapped for a spatial hash if the cap grows.

export type GraphConfig = {
  influenceRadius: number      // pointer influence radius (px)
  pointerForce: number         // base repulsion acceleration at the pointer (px/s²)
  speedBoost: number           // extra acceleration per px/s of pointer speed
  maxPointerBoost: number      // cap on that extra acceleration (px/s²)
  maxSpeed: number             // node speed cap (px/s)
  driftForce: number           // ambient drift acceleration amplitude (px/s²)
  damping: number              // velocity decay rate (1/s)
  collisionPadding: number     // extra spacing kept between capsules (px)
  collisionStiffness: number   // separation acceleration per px of overlap (px/s² per px)
  maxCollisionAccel: number    // cap on separation acceleration (px/s²)
  boundaryMargin: number       // soft wall width (px)
  boundaryForce: number        // soft wall acceleration at the wall (px/s²)
  maxDt: number                // largest simulated step (s) — tab suspension never jumps
  formationStiffness: number   // spring toward a route formation target (px/s² per px)
  formationDamping: number     // extra velocity damping while a formation pulls (1/s)
  maxFormationAccel: number    // cap on the formation pull (px/s²) — always below the pointer push
  magnetRadius: number         // reach of a hovered card's attraction (px)
  magnetForce: number          // cap on that attraction (px/s²)
  magnetMargin: number         // the attraction targets a ring this far outside the card (px)
}

export const DEFAULT_GRAPH_CONFIG: GraphConfig = {
  influenceRadius: 140,
  pointerForce: 900,
  speedBoost: 1.1,
  maxPointerBoost: 2400,
  maxSpeed: 220,
  driftForce: 7,
  damping: 1.25,
  collisionPadding: 10,
  collisionStiffness: 18,
  maxCollisionAccel: 260,
  boundaryMargin: 28,
  boundaryForce: 160,
  maxDt: 0.05,
  formationStiffness: 5,
  formationDamping: 2.2,
  maxFormationAccel: 150,
  magnetRadius: 240,
  magnetForce: 60,
  magnetMargin: 26,
}

export type GraphNode = {
  id: string
  label: string
  x: number; y: number          // centre (px)
  vx: number; vy: number        // velocity (px/s)
  w: number; h: number          // capsule size (px)
  phase: number                 // drift phase (stable per node)
  hue: 0 | 1 | 2                // accent: blue, orchid, teal — from the label, so it never shifts
  depth: 0 | 1 | 2              // apparent depth (back → front): brightness hierarchy, from the label
}

export type Bounds = { width: number; height: number }
export type Pointer = { active: boolean; x: number; y: number; speed: number }
export type Rect = { x: number; y: number; w: number; h: number }
// Optional route and hover forces. `targets[i]` is node i's formation target (null = none),
// weighted by `formation` (0–1); `magnet` is a hovered interactive card, weighted by `magnetWeight`.
export type StepForces = { targets?: ReadonlyArray<{ x: number; y: number } | null> | null; formation?: number; magnet?: Rect | null; magnetWeight?: number }

// --- deterministic randomness ------------------------------------------------------------
export function hashString(value: string): number {
  let hash = 2166136261
  for (let i = 0; i < value.length; i++) { hash ^= value.charCodeAt(i); hash = Math.imul(hash, 16777619) }
  return hash >>> 0
}
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

// Stable identity for a skill label (labels are already de-duplicated case-insensitively).
export const nodeId = (label: string) => label.toLocaleLowerCase()

// Places nodes deterministically: the same labels and bounds always give the same layout.
// Identity, hue and depth depend only on the label, never on its position in the list, so a
// data refresh that inserts or removes a skill does not recolour or re-identify the others.
export function createNodes(labels: readonly string[], measure: (label: string) => { w: number; h: number }, bounds: Bounds): GraphNode[] {
  const random = seededRandom(hashString(labels.join('|')))
  return labels.map((label) => {
    const { w, h } = measure(label)
    const halfW = Math.min(w / 2, bounds.width / 2), halfH = Math.min(h / 2, bounds.height / 2)
    const key = hashString(nodeId(label))
    return {
      id: nodeId(label), label, w, h,
      x: halfW + random() * Math.max(0, bounds.width - 2 * halfW),
      y: halfH + random() * Math.max(0, bounds.height - 2 * halfH),
      vx: (random() - 0.5) * 10, vy: (random() - 0.5) * 10,
      phase: random() * Math.PI * 2,
      hue: (key % 3) as 0 | 1 | 2,
      depth: ((key >>> 8) % 3) as 0 | 1 | 2,
    }
  })
}

// Acceleration on a node from the pointer: away from it, smooth (1 - d/r)² falloff, zero
// outside the radius, boosted by pointer speed up to a cap. Coincident points use a stable
// per-node direction instead of dividing by zero.
export function pointerAcceleration(node: GraphNode, pointer: Pointer, config: GraphConfig): { ax: number; ay: number } {
  if (!pointer.active) return { ax: 0, ay: 0 }
  const dx = node.x - pointer.x, dy = node.y - pointer.y
  const distance = Math.hypot(dx, dy)
  if (distance >= config.influenceRadius) return { ax: 0, ay: 0 }
  let ux: number, uy: number
  if (distance < 1e-6) { ux = Math.cos(node.phase); uy = Math.sin(node.phase) } else { ux = dx / distance; uy = dy / distance }
  const falloff = (1 - distance / config.influenceRadius) ** 2
  const speed = Number.isFinite(pointer.speed) ? Math.max(0, pointer.speed) : 0
  const strength = (config.pointerForce + Math.min(speed * config.speedBoost, config.maxPointerBoost)) * falloff
  return { ax: ux * strength, ay: uy * strength }
}

// Spring toward a formation target, capped well below the pointer push, so the pointer
// always wins locally and the route pull only guides the layout.
export function formationAcceleration(node: GraphNode, target: { x: number; y: number } | null | undefined, weight: number, config: GraphConfig): { ax: number; ay: number } {
  const w = Number.isFinite(weight) ? clamp(weight, 0, 1) : 0
  if (!target || w === 0 || !Number.isFinite(target.x) || !Number.isFinite(target.y)) return { ax: 0, ay: 0 }
  let ax = (target.x - node.x) * config.formationStiffness * w - node.vx * config.formationDamping * w
  let ay = (target.y - node.y) * config.formationStiffness * w - node.vy * config.formationDamping * w
  // The cap does not shrink below 60 % for weak (calm-mode) pulls, so a long relocation still
  // finishes in bounded time; near the target the spring itself stays as weak as `weight`.
  const magnitude = Math.hypot(ax, ay), cap = config.maxFormationAccel * Math.max(w, 0.6)
  if (magnitude > cap) { ax *= cap / magnitude; ay *= cap / magnitude }
  return { ax, ay }
}

// Gentle pull toward a ring just outside a hovered card (never into it): nodes within
// `magnetRadius` of the ring drift closer, with a linear falloff and a hard cap. Nodes already
// inside the ring (behind the card) get no force, so nothing is pulled through a card.
export function magnetAcceleration(node: GraphNode, magnet: Rect | null | undefined, weight: number, config: GraphConfig): { ax: number; ay: number } {
  const w = Number.isFinite(weight) ? clamp(weight, 0, 1) : 0
  if (!magnet || w === 0) return { ax: 0, ay: 0 }
  const m = config.magnetMargin + Math.max(node.w, node.h) / 2
  const left = magnet.x - m, right = magnet.x + magnet.w + m, top = magnet.y - m, bottom = magnet.y + magnet.h + m
  if (node.x > left && node.x < right && node.y > top && node.y < bottom) return { ax: 0, ay: 0 }
  const dx = clamp(node.x, left, right) - node.x, dy = clamp(node.y, top, bottom) - node.y
  const distance = Math.hypot(dx, dy)
  if (distance < 1 || distance >= config.magnetRadius) return { ax: 0, ay: 0 }
  // Zero at the ring, rising over the first 48 px, fading to zero at the reach; the approach
  // velocity is damped so a capsule eases onto the ring instead of overshooting into the card.
  const ux = dx / distance, uy = dy / distance
  const strength = config.magnetForce * w * Math.min(1, distance / 48) * (1 - distance / config.magnetRadius)
  const approach = Math.max(0, node.vx * ux + node.vy * uy)
  return { ax: ux * strength - ux * approach * 2.5 * w, ay: uy * strength - uy * approach * 2.5 * w }
}

// Gentle separation for overlapping (or too-close) capsules, along the axis of least
// overlap. Bounded acceleration plus a small positional correction so nodes never stick.
export function collide(nodes: GraphNode[], dt: number, config: GraphConfig): void {
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j]
      const dx = b.x - a.x, dy = b.y - a.y
      const overlapX = (a.w + b.w) / 2 + config.collisionPadding - Math.abs(dx)
      const overlapY = (a.h + b.h) / 2 + config.collisionPadding - Math.abs(dy)
      if (overlapX <= 0 || overlapY <= 0) continue
      const alongX = overlapX < overlapY
      const overlap = alongX ? overlapX : overlapY
      const sign = (alongX ? dx : dy) === 0 ? (i % 2 === 0 ? 1 : -1) : Math.sign(alongX ? dx : dy)
      const dv = Math.min(overlap * config.collisionStiffness, config.maxCollisionAccel) * dt
      const correction = Math.min(overlap * 0.08, 2)
      if (alongX) {
        a.vx -= sign * dv; b.vx += sign * dv
        const approach = (b.vx - a.vx) * sign
        if (approach < 0) { a.vx += sign * approach * 0.5; b.vx -= sign * approach * 0.5 }
        a.x -= sign * correction; b.x += sign * correction
      } else {
        a.vy -= sign * dv; b.vy += sign * dv
        const approach = (b.vy - a.vy) * sign
        if (approach < 0) { a.vy += sign * approach * 0.5; b.vy -= sign * approach * 0.5 }
        a.y -= sign * correction; b.y += sign * correction
      }
    }
  }
}

// Keeps a whole capsule inside the bounds: soft inward force near an edge, then a clamp
// with a damped bounce if it still crosses.
export function constrain(node: GraphNode, bounds: Bounds, dt: number, config: GraphConfig): void {
  const halfW = Math.min(node.w / 2, bounds.width / 2), halfH = Math.min(node.h / 2, bounds.height / 2)
  const minX = halfW, maxX = bounds.width - halfW, minY = halfH, maxY = bounds.height - halfH
  const margin = config.boundaryMargin
  if (node.x < minX + margin) node.vx += config.boundaryForce * (1 - (node.x - minX) / margin) * dt
  if (node.x > maxX - margin) node.vx -= config.boundaryForce * (1 - (maxX - node.x) / margin) * dt
  if (node.y < minY + margin) node.vy += config.boundaryForce * (1 - (node.y - minY) / margin) * dt
  if (node.y > maxY - margin) node.vy -= config.boundaryForce * (1 - (maxY - node.y) / margin) * dt
  if (node.x < minX) { node.x = minX; node.vx = Math.abs(node.vx) * 0.3 }
  if (node.x > maxX) { node.x = maxX; node.vx = -Math.abs(node.vx) * 0.3 }
  if (node.y < minY) { node.y = minY; node.vy = Math.abs(node.vy) * 0.3 }
  if (node.y > maxY) { node.y = maxY; node.vy = -Math.abs(node.vy) * 0.3 }
}

// One simulation step. `dt` is clamped (tab suspension, slow frames); `time` drives the
// smooth deterministic drift. Returns the fastest node speed, used to detect settling.
// Force order and weights: soft walls + hard clamp (always last), collision separation,
// pointer push (≤ pointerForce + maxPointerBoost), formation pull (≤ maxFormationAccel),
// card magnet (≤ magnetForce), drift (driftForce) — each capped so none destabilises another.
export function step(nodes: GraphNode[], dt: number, time: number, bounds: Bounds, pointer: Pointer, config: GraphConfig = DEFAULT_GRAPH_CONFIG, drift = true, forces: StepForces = {}): number {
  const h = clamp(Number.isFinite(dt) ? dt : 0, 0, config.maxDt)
  if (h === 0 || nodes.length === 0) return 0
  const decay = Math.exp(-config.damping * h)
  for (let index = 0; index < nodes.length; index++) {
    const node = nodes[index]
    let ax = 0, ay = 0
    if (drift) {
      ax += config.driftForce * Math.sin(time * 0.23 + node.phase)
      ay += config.driftForce * Math.cos(time * 0.19 + node.phase * 1.7)
    }
    const push = pointerAcceleration(node, pointer, config)
    const pull = formationAcceleration(node, forces.targets?.[index], forces.formation ?? 0, config)
    const magnet = magnetAcceleration(node, forces.magnet, forces.magnetWeight ?? 0, config)
    node.vx += (ax + push.ax + pull.ax + magnet.ax) * h
    node.vy += (ay + push.ay + pull.ay + magnet.ay) * h
  }
  collide(nodes, h, config)
  let fastest = 0
  for (const node of nodes) {
    node.vx *= decay; node.vy *= decay
    const speed = Math.hypot(node.vx, node.vy)
    if (speed > config.maxSpeed) { node.vx *= config.maxSpeed / speed; node.vy *= config.maxSpeed / speed }
    node.x += node.vx * h
    node.y += node.vy * h
    constrain(node, bounds, h, config)
    fastest = Math.max(fastest, Math.hypot(node.vx, node.vy))
  }
  return fastest
}

// A settled static layout (reduced motion, touch): relax collisions without the pointer,
// optionally held to formation targets (a static route arrangement).
export function settle(nodes: GraphNode[], bounds: Bounds, config: GraphConfig = DEFAULT_GRAPH_CONFIG, iterations = 240, targets: ReadonlyArray<{ x: number; y: number } | null> | null = null): void {
  const forces: StepForces = targets ? { targets, formation: 1 } : {}
  for (let i = 0; i < iterations; i++) step(nodes, 1 / 30, i / 30, bounds, { active: false, x: 0, y: 0, speed: 0 }, config, false, forces)
  for (const node of nodes) { node.vx = 0; node.vy = 0 }
}
