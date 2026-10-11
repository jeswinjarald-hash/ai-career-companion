// Pure geometry for the decorative skill graph: capsule boundaries, constellation-line
// trimming, foreground occlusion, open-space placement and the sleep decision. No DOM, no
// React — unit-tested in tests/unit/skillGraphSpace.test.ts. All coordinates are logical
// (CSS) pixels in the canvas space, which is the viewport (the canvas is fixed at 0,0).

export type Rect = { x: number; y: number; w: number; h: number }
// A foreground surface: 'glass' (cards, sidebar — a label-free outline may show through),
// 'solid' (text blocks, notices: nothing behind) or 'clear' (keep-clear zones such as the
// upload drop zone and the assistant composer: nothing behind, and formations avoid them).
export type Surface = Rect & { kind: 'glass' | 'solid' | 'clear' }

const finite = (value: number) => Number.isFinite(value)

// --- capsule boundary ----------------------------------------------------------------------
// Distance from a pill's centre to its outline along the unit direction (ux, uy). The pill is
// a w × h rectangle with semicircular ends (radius h/2): the set of points within h/2 of the
// central segment from (−a, 0) to (a, 0), a = w/2 − h/2. Exact, not an approximation.
export function capsuleBoundaryDistance(w: number, h: number, ux: number, uy: number): number {
  const r = Math.max(0, h / 2), a = Math.max(0, w / 2 - r)
  const length = Math.hypot(ux, uy)
  if (!(length > 0) || !finite(length)) return r
  const dx = Math.abs(ux / length), dy = Math.abs(uy / length)
  // Side wall: |t·dy| = r while |t·dx| ≤ a.
  if (dy > 1e-9) { const t = r / dy; if (t * dx <= a + 1e-9) return t }
  // End cap: |t·u − (a, 0)| = r  →  t² − 2t·a·dx + a² − r² = 0 (larger root).
  const b = a * dx
  return b + Math.sqrt(Math.max(0, b * b - a * a + r * r))
}

export type Capsule = { x: number; y: number; w: number; h: number }
export type Segment = { x0: number; y0: number; x1: number; y1: number }
// The part of the centre-to-centre line between the two capsule outlines (plus `gap` px), or
// null when the capsules touch or overlap so nothing visible would remain.
export function trimToCapsules(a: Capsule, b: Capsule, gap = 3): Segment | null {
  const ex = b.x - a.x, ey = b.y - a.y, length = Math.hypot(ex, ey)
  if (!(length > 0) || !finite(length)) return null
  const ux = ex / length, uy = ey / length
  const start = capsuleBoundaryDistance(a.w, a.h, ux, uy) + gap
  const end = length - capsuleBoundaryDistance(b.w, b.h, ux, uy) - gap
  if (!(end - start > 2)) return null
  return { x0: a.x + ux * start, y0: a.y + uy * start, x1: a.x + ux * end, y1: a.y + uy * end }
}

// --- occlusion -----------------------------------------------------------------------------
// Smallest gap between a capsule's box and any surface or the viewport edge (negative when it
// overlaps one). Used with hysteresis: a label appears only with ≥ LABEL_SHOW_CLEARANCE px of
// room and stays until the room drops below LABEL_KEEP_CLEARANCE, so it cannot flicker at an edge.
export const LABEL_SHOW_CLEARANCE = 6
export const LABEL_KEEP_CLEARANCE = 1
export function capsuleClearance(capsule: Capsule, surfaces: readonly Rect[], bounds: { width: number; height: number }): number {
  const left = capsule.x - capsule.w / 2, right = capsule.x + capsule.w / 2, top = capsule.y - capsule.h / 2, bottom = capsule.y + capsule.h / 2
  let clearance = Math.min(left, top, bounds.width - right, bounds.height - bottom)
  for (const s of surfaces) {
    const gapX = Math.max(s.x - right, left - (s.x + s.w)), gapY = Math.max(s.y - bottom, top - (s.y + s.h))
    // Separated along an axis → gap is the larger axis gap; overlapping → the (negative) depth.
    const gap = Math.max(gapX, gapY)   // separated: the larger axis gap; overlapping: minus the overlap depth
    if (gap < clearance) clearance = gap
  }
  return finite(clearance) ? clearance : -1
}
export const labelShouldShow = (showing: boolean, clearance: number): boolean =>
  clearance >= (showing ? LABEL_KEEP_CLEARANCE : LABEL_SHOW_CLEARANCE)

// Whether a segment passes through a rectangle (Liang–Barsky clip test).
export function segmentHitsRect(s: Segment, r: Rect): boolean {
  let t0 = 0, t1 = 1
  const dx = s.x1 - s.x0, dy = s.y1 - s.y0
  const checks: Array<[number, number]> = [[-dx, s.x0 - r.x], [dx, r.x + r.w - s.x0], [-dy, s.y0 - r.y], [dy, r.y + r.h - s.y0]]
  for (const [p, q] of checks) {
    if (p === 0) { if (q < 0) return false; continue }
    const t = q / p
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t } else { if (t < t0) return false; if (t < t1) t1 = t }
  }
  return t1 - t0 > 1e-9
}

// --- open-space placement ------------------------------------------------------------------
// A coarse occupancy grid of the viewport (built only when the foreground layout changes,
// never per frame): 0 = open background, 1 = behind glass, 2 = solid or keep-clear.
export type SpaceGrid = { cell: number; cols: number; rows: number; cells: Uint8Array; width: number; height: number }
export function buildSpaceGrid(bounds: { width: number; height: number }, surfaces: readonly Surface[], cell = 16): SpaceGrid {
  const cols = Math.max(1, Math.ceil(bounds.width / cell)), rows = Math.max(1, Math.ceil(bounds.height / cell))
  const cells = new Uint8Array(cols * rows)
  for (const s of surfaces) {
    const value = s.kind === 'glass' ? 1 : 2
    const c0 = Math.max(0, Math.floor(s.x / cell)), c1 = Math.min(cols - 1, Math.floor((s.x + s.w - 0.001) / cell))
    const r0 = Math.max(0, Math.floor(s.y / cell)), r1 = Math.min(rows - 1, Math.floor((s.y + s.h - 0.001) / cell))
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) if (cells[r * cols + c] < value) cells[r * cols + c] = value
  }
  return { cell, cols, rows, cells, width: bounds.width, height: bounds.height }
}

// Highest cell value under a box (2 if it leaves the grid), with an optional reserved mask.
function worstUnder(grid: SpaceGrid, x: number, y: number, w: number, h: number, reserved?: Uint8Array): number {
  if (x - w / 2 < 0 || y - h / 2 < 0 || x + w / 2 > grid.width || y + h / 2 > grid.height) return 2
  const c0 = Math.floor((x - w / 2) / grid.cell), c1 = Math.floor((x + w / 2 - 0.001) / grid.cell)
  const r0 = Math.floor((y - h / 2) / grid.cell), r1 = Math.floor((y + h / 2 - 0.001) / grid.cell)
  let worst = 0
  for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) {
    const i = r * grid.cols + c
    const value = reserved && reserved[i] ? 3 : grid.cells[i]
    if (value > worst) { worst = value; if (worst >= 2) return worst }
  }
  return worst
}
function reserve(grid: SpaceGrid, reserved: Uint8Array, x: number, y: number, w: number, h: number): void {
  const c0 = Math.max(0, Math.floor((x - w / 2) / grid.cell)), c1 = Math.min(grid.cols - 1, Math.floor((x + w / 2) / grid.cell))
  const r0 = Math.max(0, Math.floor((y - h / 2) / grid.cell)), r1 = Math.min(grid.rows - 1, Math.floor((y + h / 2) / grid.cell))
  for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) reserved[r * grid.cols + c] = 1
}

export type Placement = { x: number; y: number; open: boolean }
// Moves each formation slot to the nearest spot within `reach` px where the whole capsule
// (plus `pad`) lies in open background and does not crowd an already placed capsule; failing
// that, out of any solid/keep-clear surface (glass allowed); failing that, it stays put.
// Slots are processed in order, so earlier slots keep priority. Deterministic.
export function placeInOpenSpace(slots: ReadonlyArray<{ x: number; y: number }>, sizes: ReadonlyArray<{ w: number; h: number }>, grid: SpaceGrid, reach: number, pad = 10): Placement[] {
  const reserved = new Uint8Array(grid.cells.length)
  const step = grid.cell   // search at grid resolution: placement runs only when the layout settles
  const rings = Math.max(0, Math.ceil(reach / step))
  return slots.map((slot, i) => {
    const w = sizes[i].w + pad * 2, h = sizes[i].h + pad * 2
    const search = (accept: (value: number) => boolean): { x: number; y: number } | null => {
      if (accept(worstUnder(grid, slot.x, slot.y, w, h, reserved))) return { x: slot.x, y: slot.y }
      for (let ring = 1; ring <= rings; ring++) {
        let best: { x: number; y: number; d: number } | null = null
        for (let k = -ring; k <= ring; k++) {
          for (const [dx, dy] of [[k, -ring], [k, ring], [-ring, k], [ring, k]] as const) {
            const x = slot.x + dx * step, y = slot.y + dy * step
            const d = Math.hypot(dx, dy)
            if (best && d >= best.d) continue
            if (accept(worstUnder(grid, x, y, w, h, reserved))) best = { x, y, d }
          }
        }
        if (best) return best
      }
      return null
    }
    const open = search((value) => value === 0)
    if (open) { reserve(grid, reserved, open.x, open.y, w, h); return { x: open.x, y: open.y, open: true } }
    const notSolid = search((value) => value <= 1)
    const spot = notSolid ?? { x: slot.x, y: slot.y }
    return { x: spot.x, y: spot.y, open: false }
  })
}

// --- sleep -----------------------------------------------------------------------------------
// The loop may stop only when every animation source is quiet. Thresholds are explicit:
// node speed and per-frame movement below 0.5 px/s, pointer speed below 1 px/s.
export type SleepSignals = {
  driftFaded: boolean          // idle long enough that the ambient drift has faded out
  maxSpeed: number             // fastest node velocity (px/s)
  maxMovement: number          // fastest actual node movement over the last frame (px/s)
  pointerSpeed: number         // filtered pointer speed (px/s); a resting pointer is not motion
  transition: boolean          // a route transition is in progress
  busy: boolean                // a real request (resume analysis, assistant message) is in flight
  fading: boolean              // a node, label or line opacity is still changing
  parallaxSettling: boolean    // the parallax offset has not reached its goal
  magnetActive: boolean        // a card magnet still has weight
}
// A node pressed against a neighbour or a wall can keep a residual velocity that the collision
// or wall cancels every frame without moving it ("jammed"): below JAM_MOVEMENT of actual movement
// that counts as rest, and the engine zeroes the velocities when it sleeps.
export const SLEEP_SPEED = 0.5
export const JAM_MOVEMENT = 0.05
export function shouldSleep(s: SleepSignals): boolean {
  return s.driftFaded && !s.transition && !s.busy && !s.fading && !s.parallaxSettling && !s.magnetActive &&
    s.maxMovement < SLEEP_SPEED && (s.maxSpeed < SLEEP_SPEED || s.maxMovement < JAM_MOVEMENT) && s.pointerSpeed < 1
}

// --- pointer velocity -------------------------------------------------------------------------
// Filtered pointer speed from timestamped samples. A sample after the pointer was outside,
// or after a long gap (window refocus, teleport), only re-anchors: no velocity spike.
export const POINTER_MAX_SPEED = 5000
export const POINTER_GAP_MS = 120
export function filterPointerSpeed(previousSpeed: number, previous: { x: number; y: number; time: number; inside: boolean }, next: { x: number; y: number; time: number }): number {
  const elapsed = next.time - previous.time
  if (!previous.inside || !(elapsed > 0) || elapsed > POINTER_GAP_MS) return 0
  const instant = Math.hypot(next.x - previous.x, next.y - previous.y) / (Math.max(8, elapsed) / 1000)
  const speed = previousSpeed * 0.6 + instant * 0.4
  return finite(speed) ? Math.min(POINTER_MAX_SPEED, Math.max(0, speed)) : 0
}

// --- target separation --------------------------------------------------------------------------
// Relaxes formation targets so no two capsules' targets overlap (with `pad`, the physics'
// collision padding): a formation that asks two capsules to share space would otherwise leave
// spring and collision pushing against each other forever, and the scene could never rest.
// Pairwise push along the axis of least overlap, kept inside the bounds. Deterministic.
export function separateTargets(points: ReadonlyArray<{ x: number; y: number }>, sizes: ReadonlyArray<{ w: number; h: number }>, bounds: { width: number; height: number }, pad: number, iterations = 80): Array<{ x: number; y: number }> {
  const out = points.map((p) => ({ x: p.x, y: p.y }))
  const clampInto = (i: number) => {
    const halfW = Math.min(sizes[i].w / 2, bounds.width / 2), halfH = Math.min(sizes[i].h / 2, bounds.height / 2)
    out[i].x = Math.min(bounds.width - halfW, Math.max(halfW, out[i].x))
    out[i].y = Math.min(bounds.height - halfH, Math.max(halfH, out[i].y))
  }
  for (let iteration = 0; iteration < iterations; iteration++) {
    let moved = false
    for (let i = 0; i < out.length; i++) {
      for (let j = i + 1; j < out.length; j++) {
        const dx = out[j].x - out[i].x, dy = out[j].y - out[i].y
        const overlapX = (sizes[i].w + sizes[j].w) / 2 + pad - Math.abs(dx)
        const overlapY = (sizes[i].h + sizes[j].h) / 2 + pad - Math.abs(dy)
        if (overlapX <= 0 || overlapY <= 0) continue
        moved = true
        // Prefer separating vertically when that is cheaper (capsules are wide and short).
        if (overlapY < overlapX) { const s = (dy === 0 ? (j % 2 ? 1 : -1) : Math.sign(dy)) * (overlapY / 2 + 0.5); out[i].y -= s; out[j].y += s }
        else { const s = (dx === 0 ? (j % 2 ? 1 : -1) : Math.sign(dx)) * (overlapX / 2 + 0.5); out[i].x -= s; out[j].x += s }
        clampInto(i); clampInto(j)
      }
    }
    if (!moved) break
  }
  return out
}
