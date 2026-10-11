// Canvas 2D renderer and lifecycle for the decorative, route-aware skill graph. Physics lives
// in src/lib/skillGraphPhysics.ts, the route scene (modes, formations, edges) in
// src/lib/skillGraphScene.ts, geometry (capsule boundaries, occlusion, open-space placement,
// sleep) in src/lib/skillGraphSpace.ts; labels come only from real data (skillGraphData.ts).
//
// Modes: 'off'      — no skills, or no 2D context (never retried); nothing drawn.
//        'static'   — reduced motion or touch-only: one settled composition per route (the
//                     route's formation, placed and relaxed), no loop, no parallax, no pointer.
//        'animated' — fine pointer, motion allowed: simulation at ≤ 30 fps on the shared frame
//                     scheduler; sleeps once every animation source is quiet (shouldSleep),
//                     wakes on route or data changes, pointer movement near a capsule, a hovered
//                     interactive card, scroll, resize, layout changes or visibility.
// Route changes never recreate the engine or the nodes: they start a ~1.2 s eased transition
// from the nodes' current positions toward the new formation. Each node takes the nearest
// formation slot, and each slot is moved into nearby open background when there is room
// (placement runs on transitions, data/size changes and 250 ms after the layout settles —
// never per frame), so labelled capsules gather where the interface leaves space.
// Coordinates: one logical space in CSS pixels = the viewport (the canvas is fixed at 0,0);
// the backing store is scaled by the capped device pixel ratio. Physics positions are in that
// space; the scroll parallax offset is added at draw time and removed from the pointer.
// No React state is touched here. Capsules are pre-rendered once to offscreen sprites; lines
// use a small cache of unit-space gradients. State is mirrored to data-* attributes.
import { cancelTick, pointerFeed, requestTick, subscribePointer, subscribeScroll } from './backgroundRuntime'
import { sceneLabels, type SceneLabel } from '../lib/skillGraphData'
import { DEFAULT_GRAPH_CONFIG, createNodes, nodeId, settle, step, type Bounds, type GraphConfig, type GraphNode, type Pointer, type Rect } from '../lib/skillGraphPhysics'
import { DEFAULT_SCENE, TRANSITION_MS, assignTargets, blendParams, easeInOutCubic, edgeAlpha, formationTargets, sceneParams, selectEdges, type FormationNode, type Point, type SceneContext, type SceneParams } from '../lib/skillGraphScene'
import { buildSpaceGrid, capsuleClearance, filterPointerSpeed, labelShouldShow, placeInOpenSpace, segmentHitsRect, separateTargets, shouldSleep, trimToCapsules, type SleepSignals, type Surface } from '../lib/skillGraphSpace'

export const SKILL_GRAPH_LIMITS = { desktopNodes: 24, mobileNodes: 10, mobileWidth: 768, maxDevicePixelRatio: 1.5, fps: 30, idleMs: 8000, driftFadeMs: 3000, maxEdges: 36 }
// Scroll parallax: the graph moves up by this fraction of the page scroll, never more than
// the cap — a little depth against the fixed ambient glows, never a visible shift.
export const PARALLAX = { factor: 0.05, max: 36 }
// How far (px) a formation slot may move to reach open background; smaller on phones.
export const PLACEMENT_REACH = { desktop: 320, mobile: 96 }
const TICK = 'skill-graph'
const REDRAW_TICK = 'skill-graph-redraw'
const LAYOUT_SETTLE_MS = 250
// Foreground surfaces: behind these, capsules are drawn only as a faint label-free outline
// ("ghost"), so they read as gliding beneath the glass while no text is ever drawn behind
// content; in open background they are drawn in full. Constellation lines are drawn only in
// open background. Only the outermost match is used, so nested cards do not cancel each
// other out in the even-odd clip.
export const OCCLUDER_SELECTOR = '.sidebar, .topbar, .drawer, .card, .page-heading > *, .architecture-note, .error-notice, .success-notice, .long-task, .result-summary, .detail-actions'
// Of those, only surfaces dense enough to dim what is behind them get ghosts; text and notices
// that sit directly on the background (headings, notices, action rows) get nothing at all.
const GLASS_SELECTOR = '.sidebar, .topbar, .drawer, .card'
// Text wrappers that are full-width blocks: measured by the tight bounds of their text (plus
// TEXT_PAD), so the open space beside a short heading is recognised as open.
const TEXT_BLOCK_SELECTOR = '.page-heading > div:not(.page-heading-action)'
const TEXT_PAD = 8
// Keep-clear zones (opt-in metadata): nothing is drawn behind them, not even an outline, and
// placement moves slots out of them. Anchors: the route's main surface a formation is laid out around.
export const KEEP_CLEAR_SELECTOR = '[data-graph-keep-clear]'
export const ANCHOR_SELECTOR = '[data-graph-anchor]'
const FRAME_MS = 1000 / SKILL_GRAPH_LIMITS.fps
const FADE_MS = 500
const MOBILE_UNPLACED_ALPHA = 0.4   // phones: capsules with no open space stay quiet behind panels
const DEPTH_ALPHA = [0.7, 0.85, 1]  // back → front brightness hierarchy
const HUES: Array<[number, number, number]> = [[96, 128, 255], [168, 112, 255], [72, 214, 230]]   // indigo, violet, cyan
const GAP_HUE: [number, number, number] = [255, 186, 104]   // amber: a real reported gap (also dashed)
type Mode = 'off' | 'static' | 'animated'
type Sprite = { image: HTMLCanvasElement; ghost: HTMLCanvasElement; width: number; height: number }
type Transition = { from: SceneParams; to: SceneParams; elapsed: number; starts: Map<string, Point> }
type Exiting = { node: GraphNode; sprite: Sprite; alpha: number }
const sameParams = (a: SceneParams, b: SceneParams) => a.formation === b.formation && a.drift === b.drift && a.linkRadius === b.linkRadius && a.linkAlpha === b.linkAlpha && a.linksPerNode === b.linksPerNode
const edgeKey = (a: string, b: string) => (a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`)

export class SkillGraphEngine {
  private readonly canvas: HTMLCanvasElement
  private readonly ctx: CanvasRenderingContext2D | null
  private readonly config: GraphConfig = { ...DEFAULT_GRAPH_CONFIG }
  private readonly pointer: Pointer = { active: false, x: 0, y: 0, speed: 0 }
  private readonly finePointer = window.matchMedia('(hover: hover) and (pointer: fine)')
  private readonly reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  private allSkills: readonly string[] = []
  private scene: SceneContext = DEFAULT_SCENE
  private params: SceneParams = sceneParams(DEFAULT_SCENE)
  private transition: Transition | null = null
  private labels: SceneLabel[] = []
  private nodes: GraphNode[] = []
  private formationInfo: FormationNode[] = []
  private gapIds = new Set<string>()
  private alpha = new Map<string, number>()          // per-node presence (0–1), eased toward alphaGoal
  private alphaGoal = new Map<string, number>()
  private labelOn = new Map<string, boolean>()       // label state with clearance hysteresis
  private labelAlpha = new Map<string, number>()     // 1 = labelled capsule, 0 = label-free outline
  private exiting: Exiting[] = []
  private edgeAlphas = new Map<string, number>()     // smoothed line opacity, by label pair
  private targets: Array<Point | null> | null = null
  private slots: number[] | null = null              // formation slot per node (stable until re-placed)
  private slotOffsets: Point[] = []                  // open-space placement offset per slot
  private slotOpen: boolean[] = []                   // whether the slot reached open background
  private sprites = new Map<string, Sprite>()        // by `${id}|gap|small|dpr` — reused across data changes
  private gradients = new Map<string, CanvasGradient>()
  private bounds: Bounds = { width: 0, height: 0 }
  private dpr = 1
  private mode: Mode = 'off'
  private running = false
  private lastFrame = 0
  private lastActivity = 0
  private simTime = 0
  private orbitTime = 0
  private parallax = 0
  private parallaxTarget = 0
  private magnet: Rect | null = null
  private magnetWeight = 0
  private magnetSuppressedAt = -1                    // pointer sample time when a route change hid the magnet
  private lastSample = { x: 0, y: 0, time: 0, inside: false }
  private lastSignals: SleepSignals | null = null   // the last frame's sleep inputs (diagnostics/tests)
  private lastRematch = 0
  private previous = new Float64Array(0)             // positions before the last step (movement measure)
  private resizeObserver: ResizeObserver | null = null
  private layoutObserver: ResizeObserver | null = null
  private mutationObserver: MutationObserver | null = null
  private surfaces: Surface[] = []
  private anchor: Rect | null = null
  private occludersDirty = true
  private redrawOnVisible = false
  private placeOnVisible = false
  private layoutTimer: ReturnType<typeof setTimeout> | null = null
  private destroyed = false
  private unsubscribePointer: () => void = () => undefined
  private unsubscribeScroll: () => void = () => undefined

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
    let context: CanvasRenderingContext2D | null = null
    try { context = canvas.getContext('2d') } catch { context = null }
    this.ctx = context
    this.canvas.dataset.scene = this.scene.mode
    if (!this.ctx) { this.setData('off', 'stopped', 'no-context'); return }
    this.measure()
    this.finePointer.addEventListener('change', this.applyMode)
    this.reducedMotion.addEventListener('change', this.applyMode)
    document.addEventListener('visibilitychange', this.onVisibility)
    if (typeof ResizeObserver === 'function') { this.resizeObserver = new ResizeObserver(this.onResize); this.resizeObserver.observe(canvas) }
    else window.addEventListener('resize', this.onResize)
    this.unsubscribePointer = subscribePointer(this.onPointer)
    // Foreground layout changes (scroll, data loading, route changes) re-read the surfaces once
    // on the next frame and re-place the formation once the layout has settled — never per frame.
    this.unsubscribeScroll = subscribeScroll(this.onScroll)
    if (typeof MutationObserver === 'function') { this.mutationObserver = new MutationObserver(this.onLayoutChange); this.mutationObserver.observe(document.body, { childList: true, subtree: true }) }
    if (typeof ResizeObserver === 'function') { this.layoutObserver = new ResizeObserver(this.onLayoutChange); this.layoutObserver.observe(document.body) }
  }

  setSkills(skills: readonly string[]): void {
    this.allSkills = skills
    this.rebuild()
  }

  // Route identity and real request/gap state. Updates targets and parameters only — the
  // engine, canvas and existing nodes stay.
  setScene(next: SceneContext): void {
    const previous = this.scene
    if (next === previous) return
    this.scene = next
    this.canvas.dataset.scene = next.mode
    if (!this.ctx) return
    if (next.mode !== previous.mode) this.magnetSuppressedAt = pointerFeed.latest.time   // the hovered card belonged to the old screen
    const target = sceneParams(next)
    if (next.mode !== previous.mode || !sameParams(target, sceneParams(previous))) this.startTransition(target)
    const gapsChanged = next.gapSkills !== previous.gapSkills || (next.mode === 'skillGaps') !== (previous.mode === 'skillGaps')
    if (gapsChanged) this.rebuild()
    else if (this.mode === 'static') this.layoutStatic()
    else if (this.mode === 'animated') this.wake()
  }

  destroy(): void {
    this.destroyed = true
    this.stop('stopped')
    this.finePointer.removeEventListener('change', this.applyMode)
    this.reducedMotion.removeEventListener('change', this.applyMode)
    document.removeEventListener('visibilitychange', this.onVisibility)
    this.resizeObserver?.disconnect()
    this.layoutObserver?.disconnect()
    this.mutationObserver?.disconnect()
    this.unsubscribeScroll()
    if (this.layoutTimer) clearTimeout(this.layoutTimer)
    this.layoutTimer = null
    cancelTick(REDRAW_TICK)
    window.removeEventListener('resize', this.onResize)
    this.unsubscribePointer()
  }

  // Read-only view for development diagnostics and e2e tests (exposed only in dev builds).
  snapshot() {
    const position = new Map(this.nodes.map((node) => [node.label, node]))
    return {
      mode: this.mode, running: this.running, bounds: { ...this.bounds }, dpr: this.dpr,
      scene: this.scene.mode, params: { ...this.params },
      transition: this.transition ? Math.min(1, this.transition.elapsed / TRANSITION_MS) : null,
      parallax: this.parallax, magnetWeight: this.magnetWeight,
      nodes: this.nodes.map(({ id, label, x, y, vx, vy, w, h, depth }, i) => ({
        id, label, x, y, vx, vy, w, h, depth, gap: this.gapIds.has(id), alpha: this.alpha.get(id) ?? 1,
        labelAlpha: this.labelAlpha.get(id) ?? 0, placedOpen: this.slots ? this.slotOpen[this.slots[i]] ?? false : false,
      })),
      targets: this.targets ? this.targets.map((point) => (point ? { ...point } : null)) : null,
      edges: Array.from(this.edgeAlphas, ([key, alpha]) => {
        const [a, b] = key.split('\u0000')
        const na = this.nodes.find((n) => n.id === a), nb = this.nodes.find((n) => n.id === b)
        return { a: na?.label ?? a, b: nb?.label ?? b, alpha, distance: na && nb ? Math.hypot(na.x - nb.x, na.y - nb.y) : null }
      }),
      surfaces: this.surfaces.length, signals: this.lastSignals ? { ...this.lastSignals } : null,
      anchor: this.anchor ? { ...this.anchor } : null,
      labels: position.size,
    }
  }

  // --- data and layout -----------------------------------------------------------------------
  private small(): boolean { return this.bounds.width < SKILL_GRAPH_LIMITS.mobileWidth }

  private nodeCap(): number {
    return this.small() || !this.finePointer.matches ? SKILL_GRAPH_LIMITS.mobileNodes : SKILL_GRAPH_LIMITS.desktopNodes
  }

  // Gap labels are used only on the skill-gap screens, and only when that screen published
  // a real analysis (see SkillsView).
  private wantedLabels(): SceneLabel[] {
    return sceneLabels(this.allSkills, this.scene.mode === 'skillGaps' ? this.scene.gapSkills : [], this.nodeCap())
  }

  private rebuild(): void {
    if (!this.ctx) return
    const labels = this.wantedLabels()
    const same = labels.length === this.labels.length && labels.every((entry, i) => entry.label === this.labels[i].label && entry.gap === this.labels[i].gap)
    if (!same) {
      const animated = this.mode === 'animated'
      const previous = new Map(this.nodes.map((node) => [node.id, node]))
      const kept = new Set(labels.map((entry) => nodeId(entry.label)))
      // Labels that leave fade out where they are (animated); sign-out or an empty list clears at once.
      this.exiting = animated && labels.length > 0
        ? [...this.exiting, ...this.nodes.filter((node) => !kept.has(node.id)).flatMap((node) => { const sprite = this.sprites.get(this.spriteKey(node)); return sprite ? [{ node, sprite, alpha: this.alpha.get(node.id) ?? 1 }] : [] })]
        : []
      const keptAlpha = new Map(this.nodes.map((node) => [node.id, this.alpha.get(node.id) ?? 1]))
      const keptLabel = new Map(this.nodes.map((node) => [node.id, { on: this.labelOn.get(node.id) ?? false, alpha: this.labelAlpha.get(node.id) ?? 0 }]))
      this.labels = labels
      this.nodes = createNodes(labels.map((entry) => entry.label), (label) => this.capsuleSize(label), this.bounds)
      this.gapIds = new Set(this.nodes.filter((_, i) => labels[i].gap).map((node) => node.id))
      this.formationInfo = this.nodes.map((node) => ({ w: node.w, h: node.h, gap: this.gapIds.has(node.id) }))
      this.alpha.clear(); this.alphaGoal.clear(); this.labelOn.clear(); this.labelAlpha.clear()
      // Nodes that stay keep their identity, place and state (no jump); new ones are relaxed into free space and fade in.
      const fresh = this.nodes.filter((node) => !previous.has(node.id))
      if (fresh.length) settle(fresh, this.bounds, this.config, 60)
      for (const node of this.nodes) {
        const old = previous.get(node.id)
        if (old) { node.x = old.x; node.y = old.y; node.vx = old.vx; node.vy = old.vy }
        this.alpha.set(node.id, old ? keptAlpha.get(node.id) ?? 1 : animated && previous.size > 0 ? 0 : 1)
        this.alphaGoal.set(node.id, 1)
        const label = keptLabel.get(node.id)
        if (label) { this.labelOn.set(node.id, label.on); this.labelAlpha.set(node.id, label.alpha) }
        this.ensureSprite(node)
      }
      for (const key of [...this.edgeAlphas.keys()]) { const [a, b] = key.split('\u0000'); if (!kept.has(a) || !kept.has(b)) this.edgeAlphas.delete(key) }
      this.previous = new Float64Array(this.nodes.length * 2)
      this.assignSlots()
    }
    this.applyMode()
  }

  private capsuleSize(label: string): { w: number; h: number } {
    const small = this.small()
    this.ctx!.font = this.font(small)
    return { w: Math.ceil(this.ctx!.measureText(label).width) + (small ? 20 : 24), h: small ? 22 : 24 }
  }

  private font(small: boolean): string { return `500 ${small ? 11 : 12}px "Segoe UI", system-ui, sans-serif` }

  private spriteKey(node: GraphNode): string { return `${node.id}|${this.gapIds.has(node.id) ? 1 : 0}|${this.small() ? 1 : 0}|${this.dpr}` }

  private ensureSprite(node: GraphNode): Sprite {
    const key = this.spriteKey(node)
    let sprite = this.sprites.get(key)
    if (!sprite) {
      const pad = 6
      const width = node.w + pad * 2, height = node.h + pad * 2
      const gap = this.gapIds.has(node.id)
      sprite = { image: this.paintCapsule(node, pad, width, height, false, gap), ghost: this.paintCapsule(node, pad, width, height, true, gap), width, height }
      this.sprites.set(key, sprite)
      if (this.sprites.size > 96) { const oldest = this.sprites.keys().next().value; if (oldest !== undefined) this.sprites.delete(oldest) }   // bounded cache
    }
    return sprite
  }

  // One offscreen sprite per capsule: translucent glass fill, a soft top sheen, a thin
  // gradient outline with a restrained glow, and the label (omitted for the ghost outline).
  private paintCapsule(node: GraphNode, pad: number, width: number, height: number, ghost: boolean, gap: boolean): HTMLCanvasElement {
    const image = document.createElement('canvas')
    image.width = Math.ceil(width * this.dpr); image.height = Math.ceil(height * this.dpr)
    const g = image.getContext('2d')
    if (g) {
      g.scale(this.dpr, this.dpr)
      const [r, gr, b] = gap ? GAP_HUE : HUES[node.hue], [r2, g2, b2] = gap ? HUES[1] : HUES[(node.hue + 1) % 3]
      const radius = node.h / 2
      const pill = () => {
        g.beginPath()
        g.moveTo(pad + radius, pad); g.lineTo(pad + node.w - radius, pad)
        g.arc(pad + node.w - radius, pad + radius, radius, -Math.PI / 2, Math.PI / 2)
        g.lineTo(pad + radius, pad + node.h)
        g.arc(pad + radius, pad + radius, radius, Math.PI / 2, (3 * Math.PI) / 2)
        g.closePath()
      }
      pill()
      const fill = g.createLinearGradient(0, pad, 0, pad + node.h)
      fill.addColorStop(0, `rgba(${r}, ${gr}, ${b}, ${ghost ? 0.045 : 0.1})`)
      fill.addColorStop(1, `rgba(12, 16, 34, ${ghost ? 0.02 : 0.28})`)
      g.fillStyle = fill
      g.fill()
      if (!ghost) {
        // Glass sheen: a faint highlight across the upper half, clipped to the pill.
        g.save(); pill(); g.clip()
        const sheen = g.createLinearGradient(0, pad, 0, pad + node.h / 2)
        sheen.addColorStop(0, 'rgba(255, 255, 255, 0.09)')
        sheen.addColorStop(1, 'rgba(255, 255, 255, 0)')
        g.fillStyle = sheen
        g.fillRect(pad, pad, node.w, node.h / 2)
        g.restore()
      }
      pill()
      const outline = g.createLinearGradient(pad, pad, pad + node.w, pad + node.h)
      outline.addColorStop(0, `rgba(${r}, ${gr}, ${b}, ${ghost ? 0.55 : 0.55})`)
      outline.addColorStop(1, `rgba(${r2}, ${g2}, ${b2}, ${ghost ? 0.25 : 0.24})`)
      g.shadowColor = `rgba(${r}, ${gr}, ${b}, 0.28)`
      g.shadowBlur = 6
      g.lineWidth = 1
      g.strokeStyle = outline
      if (gap) g.setLineDash([4, 3])   // gaps differ by outline style as well as colour
      g.stroke()
      g.setLineDash([])
      g.shadowBlur = 0
      if (!ghost) {
        g.font = this.font(this.small())
        g.textAlign = 'center'; g.textBaseline = 'middle'
        g.fillStyle = gap ? 'rgba(255, 228, 196, 0.72)' : 'rgba(220, 228, 255, 0.72)'
        g.fillText(node.label, pad + node.w / 2, pad + node.h / 2 + 0.5)
      }
    }
    return image
  }

  private measure(): void {
    const width = this.canvas.clientWidth, height = this.canvas.clientHeight
    const dpr = Math.min(window.devicePixelRatio || 1, SKILL_GRAPH_LIMITS.maxDevicePixelRatio)
    if (dpr !== this.dpr) { this.sprites.clear(); this.gradients.clear() }
    this.dpr = dpr
    this.bounds = { width, height }
    this.canvas.width = Math.max(1, Math.round(width * this.dpr))
    this.canvas.height = Math.max(1, Math.round(height * this.dpr))
    this.ctx?.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this.gradients.clear()   // resizing the backing store resets context state
  }

  // --- scene transitions and placement ---------------------------------------------------------
  private startTransition(to: SceneParams): void {
    // From the current (possibly mid-transition) state, never from a stored origin.
    this.transition = { from: { ...this.params }, to, elapsed: 0, starts: new Map(this.nodes.map((node) => [node.id, { x: node.x, y: node.y }])) }
    this.assignSlots()
  }

  // Each node takes the nearest formation slot, then each slot is moved into nearby open
  // background where there is room for that node's actual capsule (a fixed offset per slot,
  // so moving formations keep their shape; placed capsules never overlap). Runs on
  // transitions, data/size changes and once the layout settles — never per frame.
  private assignSlots(): void {
    if (this.occludersDirty) this.readOccluders()
    const raw = formationTargets(this.scene.mode, this.formationInfo, this.bounds, this.orbitTime, this.formationContext())
    if (!raw) { this.slots = null; this.slotOffsets = []; this.slotOpen = []; return }
    this.slots = assignTargets(this.nodes, raw)
    const sizeOfSlot = new Array<{ w: number; h: number }>(raw.length).fill({ w: 80, h: 24 })
    this.slots.forEach((slot, i) => { sizeOfSlot[slot] = { w: this.nodes[i].w, h: this.nodes[i].h } })
    const grid = buildSpaceGrid(this.bounds, this.surfaces)
    const placed = placeInOpenSpace(raw, sizeOfSlot, grid, this.small() ? PLACEMENT_REACH.mobile : PLACEMENT_REACH.desktop)
    // No two targets may ask capsules to share space (margin keeps them off the edges too).
    const margin = 16
    const spread = separateTargets(placed, sizeOfSlot.map((size) => ({ w: size.w + margin * 2, h: size.h + margin * 2 })), this.bounds, this.config.collisionPadding + 2 - margin * 2)
    this.slotOffsets = spread.map((spot, i) => ({ x: spot.x - raw[i].x, y: spot.y - raw[i].y }))
    this.slotOpen = placed.map((spot) => spot.open)
    // Phones: capsules that found no open space stay quiet behind the panels.
    this.nodes.forEach((node, i) => this.alphaGoal.set(node.id, this.small() && !this.slotOpen[this.slots![i]] ? MOBILE_UNPLACED_ALPHA : 1))
  }

  private formationContext() {
    return { assistantPending: this.scene.assistantPending, resumeProcessing: this.scene.resumeProcessing, anchor: this.anchor }
  }

  // This frame's placed formation, per node.
  private formation(time: number): Point[] | null {
    const raw = formationTargets(this.scene.mode, this.formationInfo, this.bounds, time, this.formationContext())
    const order = this.slots
    if (!raw || !order || order.length !== raw.length) return raw
    const margin = 16
    return this.nodes.map((node, i) => {
      const slot = order[i], offset = this.slotOffsets[slot]
      const point = raw[slot] ?? raw[i]
      const x = point.x + (offset?.x ?? 0), y = point.y + (offset?.y ?? 0)
      // Clamped with this node's own size (slots were placed for a typical capsule), so a
      // wide capsule is never pulled against the viewport edge.
      const halfW = Math.min(node.w / 2 + margin, this.bounds.width / 2), halfH = Math.min(node.h / 2 + margin, this.bounds.height / 2)
      return { x: Math.min(this.bounds.width - halfW, Math.max(halfW, x)), y: Math.min(this.bounds.height - halfH, Math.max(halfH, y)) }
    })
  }

  // Targets for this frame: the placed route formation, approached from each node's position
  // at the start of the transition along the eased progress.
  private computeTargets(eased: number): Array<Point | null> | null {
    const placed = this.formation(this.orbitTime)
    if (!placed) return null
    const transition = this.transition
    if (!transition) return placed
    return this.nodes.map((node, i) => {
      const start = transition.starts.get(node.id) ?? { x: node.x, y: node.y }
      return { x: start.x + (placed[i].x - start.x) * eased, y: start.y + (placed[i].y - start.y) * eased }
    })
  }

  // Reduced motion / touch: the route's arrangement as one settled frame — no animation,
  // no interpolation, no parallax. Starts from the deterministic seeded layout every time.
  private layoutStatic(): void {
    if (!this.ctx || this.mode !== 'static') return
    this.transition = null
    this.params = sceneParams(this.scene)
    this.parallax = 0; this.parallaxTarget = 0; this.magnetWeight = 0; this.magnet = null
    this.exiting = []
    if (this.occludersDirty) this.readOccluders()
    const home = createNodes(this.nodes.map((node) => node.label), (label) => this.capsuleSize(label), this.bounds)
    this.nodes.forEach((node, i) => { node.x = home[i].x; node.y = home[i].y; node.vx = 0; node.vy = 0 })
    this.orbitTime = 0
    this.assignSlots()
    const targets = this.params.formation > 0 ? this.computeTargets(1) : null
    if (targets) this.nodes.forEach((node, i) => { node.x = targets[i]!.x; node.y = targets[i]!.y })
    this.targets = targets
    settle(this.nodes, this.bounds, this.config, 240, targets)
    for (const node of this.nodes) this.alpha.set(node.id, this.alphaGoal.get(node.id) ?? 1)
    this.updateLabels(Infinity)
    this.updateEdges(0, true)
    if (document.hidden) { this.redrawOnVisible = true; return }
    this.draw()
  }

  // --- modes and loop ------------------------------------------------------------------------
  private readonly applyMode = (): void => {
    if (!this.ctx || this.destroyed) return
    const next: Mode = this.labels.length === 0 ? 'off' : this.reducedMotion.matches || !this.finePointer.matches ? 'static' : 'animated'
    const capChanged = this.wantedLabels().length !== this.labels.length
    if (capChanged) { this.rebuild(); return }
    this.mode = next
    if (next === 'off') { this.stop('stopped'); this.exiting = []; this.edgeAlphas.clear(); this.ctx.clearRect(0, 0, this.bounds.width, this.bounds.height); this.setEdgeCount(0); this.setData('off', 'stopped'); return }
    if (next === 'static') { this.stop('stopped'); this.setData('static', 'stopped'); this.layoutStatic(); return }
    this.setData('animated', this.running ? 'running' : this.canvas.dataset.loop ?? 'stopped')
    this.draw()
    this.wake()
  }

  private wake(activity = true): void {
    if (this.mode !== 'animated' || document.hidden || this.destroyed) return
    if (activity) this.lastActivity = performance.now()
    if (this.running) return
    this.running = true
    this.lastFrame = 0
    this.setData('animated', 'running')
    requestTick(TICK, this.tick)
  }

  private stop(loop: 'idle' | 'paused' | 'stopped'): void {
    this.running = false
    cancelTick(TICK)
    this.canvas.dataset.loop = loop
  }

  private readonly tick = (time: number): void => {
    if (!this.running) return
    if (this.lastFrame && time - this.lastFrame < FRAME_MS - 1) { requestTick(TICK, this.tick); return }   // ≤ 30 fps
    const dt = this.lastFrame ? (time - this.lastFrame) / 1000 : 1 / SKILL_GRAPH_LIMITS.fps
    const h = Math.min(Math.max(0, Number.isFinite(dt) ? dt : 0), this.config.maxDt)   // suspension never jumps
    this.lastFrame = time
    this.simTime += h
    if (this.occludersDirty) this.readOccluders()

    // Scene transition: progress by clamped simulated time, eased; parameters blended.
    let eased = 1
    if (this.transition) {
      this.transition.elapsed += h * 1000
      eased = easeInOutCubic(this.transition.elapsed / TRANSITION_MS)
      this.params = blendParams(this.transition.from, this.transition.to, eased)
    }
    // Parallax and magnet ease toward their goals (no jumps on fast scrolls or hover changes).
    this.parallax += (this.parallaxTarget - this.parallax) * Math.min(1, h * 8)
    if (Math.abs(this.parallaxTarget - this.parallax) < 0.05) this.parallax = this.parallaxTarget
    this.updateMagnet(h)

    this.readPointer(time, h)
    const idleFor = time - this.lastActivity
    // After the idle interval the drift (and the slow orbit/stream sway) fades out, so the
    // scene comes to rest instead of moving forever; the pointer still pushes while near.
    const fade = Math.min(1, Math.max(0, (idleFor - SKILL_GRAPH_LIMITS.idleMs) / SKILL_GRAPH_LIMITS.driftFadeMs))
    const busy = (this.scene.mode === 'assistant' && this.scene.assistantPending) || (this.scene.mode === 'resume' && this.scene.resumeProcessing)
    this.orbitTime += h * (busy ? 1 : 1 - fade)
    this.config.driftForce = DEFAULT_GRAPH_CONFIG.driftForce * this.params.drift * (1 - fade)
    this.targets = this.params.formation > 0 ? this.computeTargets(eased) : null
    const before = this.previous
    this.nodes.forEach((node, i) => { before[i * 2] = node.x; before[i * 2 + 1] = node.y })
    const fastest = step(this.nodes, h, this.simTime, this.bounds, this.pointer, this.config, true, { targets: this.targets, formation: this.params.formation, magnet: this.magnet, magnetWeight: this.magnetWeight })
    let moved = 0
    if (h > 0) this.nodes.forEach((node, i) => { moved = Math.max(moved, Math.hypot(node.x - before[i * 2], node.y - before[i * 2 + 1]) / h) })
    if (this.transition && this.transition.elapsed >= TRANSITION_MS) { this.params = this.transition.to; this.transition = null }
    this.recoverFromJam(time, moved)

    // Presence fades: nodes that arrived or left with a data change, phone dimming.
    let fading = false
    const rate = (h * 1000) / FADE_MS
    for (const node of this.nodes) {
      const a = this.alpha.get(node.id) ?? 1, goal = this.alphaGoal.get(node.id) ?? 1
      if (a !== goal) { this.alpha.set(node.id, Math.abs(goal - a) <= rate ? goal : a + Math.sign(goal - a) * rate); fading = true }
    }
    for (const leaving of this.exiting) leaving.alpha -= rate
    this.exiting = this.exiting.filter((leaving) => leaving.alpha > 0)
    if (this.exiting.length) fading = true
    if (this.updateLabels(h)) fading = true
    if (this.updateEdges(h, false)) fading = true
    this.draw()
    this.lastSignals = {
      driftFaded: fade >= 1, maxSpeed: fastest, maxMovement: moved, pointerSpeed: this.pointer.speed,
      transition: this.transition !== null, busy, fading,
      parallaxSettling: this.parallax !== this.parallaxTarget, magnetActive: this.magnetWeight > 0,
    }
    if (shouldSleep(this.lastSignals)) { for (const node of this.nodes) { node.vx = 0; node.vy = 0 } this.stop('idle'); return }   // at rest: no residual velocity kept
    requestTick(TICK, this.tick)
  }

  // Jam recovery: two capsules heading for each other's side (assigned before they met) stop
  // short of their targets. When nothing makes progress but targets are still far, re-match
  // nodes to the already-placed slots from where they are now (shorter-total matching swaps
  // such pairs). Rate-limited, only while jammed — never per frame.
  private recoverFromJam(time: number, moved: number): void {
    if (this.transition || !this.targets || !this.slots || moved >= 3 || time - this.lastRematch < 1200) return
    let worst = 0
    this.nodes.forEach((node, i) => { const t = this.targets![i]; if (t) worst = Math.max(worst, Math.hypot(node.x - t.x, node.y - t.y)) })
    if (worst <= 24) return
    this.lastRematch = time
    const placed = this.formation(this.orbitTime)
    if (!placed) return
    const bySlot = new Array<Point>(placed.length)
    this.slots.forEach((slot, i) => { bySlot[slot] = placed[i] })
    if (bySlot.some((point) => !point)) return
    const next = assignTargets(this.nodes, bySlot)
    if (next.every((slot, i) => slot === this.slots![i])) return
    this.slots = next
    this.lastActivity = Math.max(this.lastActivity, time - SKILL_GRAPH_LIMITS.idleMs)   // keep stepping until resolved
  }

  // The hovered interactive card (from the shared pointer feed). Dropped when its element is
  // gone (unmounted by a route change) or until the pointer moves after a route change.
  private updateMagnet(h: number): void {
    const element = pointerFeed.magnetElement
    const stale = (element !== null && !element.isConnected) || pointerFeed.latest.time === this.magnetSuppressedAt
    const source = stale ? null : pointerFeed.magnet
    const goal = source && pointerFeed.latest.inside ? 1 : 0
    if (source) this.magnet = { ...source, y: source.y - this.parallax }
    this.magnetWeight += (goal - this.magnetWeight) * Math.min(1, h * 5)
    if (goal === 0 && this.magnetWeight < 0.01) { this.magnetWeight = 0; this.magnet = null }
  }

  private readPointer(time: number, dt: number): void {
    const sample = pointerFeed.latest
    this.pointer.active = sample.inside
    this.pointer.x = sample.x; this.pointer.y = sample.y - this.parallax   // viewport → graph space
    if (sample.time !== this.lastSample.time) {
      // Re-anchors without a spike after the pointer was outside or after a long gap.
      this.pointer.speed = filterPointerSpeed(this.pointer.speed, this.lastSample, sample)
      this.lastSample = { x: sample.x, y: sample.y, time: sample.time, inside: sample.inside }
      if (this.pointerNear()) this.lastActivity = time
    } else {
      this.pointer.speed *= Math.exp(-dt * 6)
      if (this.pointer.speed < 0.01) this.pointer.speed = 0
    }
    if (!sample.inside) this.pointer.speed = 0
  }

  private pointerNear(): boolean {
    if (!this.pointer.active) return false
    const reach = this.config.influenceRadius * 1.5
    return this.nodes.some((node) => Math.abs(node.x - this.pointer.x) < reach && Math.abs(node.y - this.pointer.y) < reach)
  }

  // Label state per capsule (at its drawn position): shown only while the whole capsule has
  // clearance from every surface and the viewport edge (with hysteresis), then crossfaded.
  // Returns whether a crossfade is still running.
  private updateLabels(h: number): boolean {
    let moving = false
    const rate = Number.isFinite(h) ? Math.min(1, h * 7) : 1
    for (const node of this.nodes) {
      const clearance = capsuleClearance({ x: node.x, y: node.y + this.parallax, w: node.w, h: node.h }, this.surfaces, this.bounds)
      const on = labelShouldShow(this.labelOn.get(node.id) ?? false, clearance)
      this.labelOn.set(node.id, on)
      const goal = on ? 1 : 0, current = this.labelAlpha.get(node.id) ?? goal
      const next = Math.abs(goal - current) < 0.02 ? goal : current + (goal - current) * rate
      if (next !== goal) moving = true
      this.labelAlpha.set(node.id, next)
    }
    return moving
  }

  // Constellation: nearby pairs within the scene's radius and per-node cap (lines drawn last
  // frame keep priority). A line shows only between two labelled capsules and never across a
  // foreground surface; opacities are smoothed so lines fade instead of popping. Returns
  // whether any line is still fading.
  private updateEdges(h: number, immediate: boolean): boolean {
    const ids = this.nodes.map((node) => node.id)
    const edges = selectEdges(this.nodes, this.params.linkRadius, this.params.linksPerNode, SKILL_GRAPH_LIMITS.maxEdges, (a, b) => this.edgeAlphas.has(edgeKey(ids[a], ids[b])))
    const goal = new Map<string, number>()
    const reach = this.config.influenceRadius * 1.5
    const dy = this.parallax
    for (const edge of edges) {
      const a = this.nodes[edge.a], b = this.nodes[edge.b]
      const visible = Math.min(this.labelAlpha.get(a.id) ?? 0, this.labelAlpha.get(b.id) ?? 0)
      if (visible <= 0) continue
      const segment = trimToCapsules({ x: a.x, y: a.y + dy, w: a.w, h: a.h }, { x: b.x, y: b.y + dy, w: b.w, h: b.h })
      if (!segment || this.surfaces.some((surface) => segmentHitsRect(segment, surface))) continue
      const near = this.pointer.active && this.mode === 'animated' ? Math.max(0, 1 - Math.hypot((a.x + b.x) / 2 - this.pointer.x, (a.y + b.y) / 2 - this.pointer.y) / reach) : 0
      goal.set(edgeKey(a.id, b.id), edgeAlpha(edge.strength, this.params.linkAlpha, near) * visible)
    }
    if (immediate) { this.edgeAlphas = goal; return false }
    let moving = false
    const rate = Math.min(1, h * 6)
    for (const key of new Set([...this.edgeAlphas.keys(), ...goal.keys()])) {
      const current = this.edgeAlphas.get(key) ?? 0, target = goal.get(key) ?? 0
      const next = current + (target - current) * rate
      if (target === 0 && next < 0.004) { this.edgeAlphas.delete(key); if (current > 0.004) moving = true; continue }
      const done = Math.abs(target - next) <= 0.004
      if (!done) moving = true
      this.edgeAlphas.set(key, done ? target : next)
    }
    return moving
  }

  private draw(): void {
    if (!this.ctx) return
    if (this.occludersDirty) { this.readOccluders(); this.updateLabels(Infinity) }
    const ctx = this.ctx
    ctx.clearRect(0, 0, this.bounds.width, this.bounds.height)
    if (this.nodes.length === 0 && this.exiting.length === 0) { this.setEdgeCount(0); return }
    const dy = this.parallax
    const glass = this.surfaces.filter((surface) => surface.kind === 'glass')
    const blocking = this.surfaces.filter((surface) => surface.kind !== 'clear')
    // Behind glass surfaces: label-free ghosts only (nothing behind bare text blocks, no lines).
    if (glass.length) {
      ctx.save()
      ctx.beginPath()
      for (const box of glass) ctx.rect(box.x, box.y, box.w, box.h)
      ctx.clip()
      for (const leaving of this.exiting) this.drawSprite(leaving.sprite.ghost, leaving.sprite, leaving.node, dy, leaving.alpha)
      for (const node of this.nodes) this.drawSprite(this.ensureSprite(node).ghost, this.ensureSprite(node), node, dy, this.alpha.get(node.id) ?? 1)
      ctx.restore()
    }
    // Open background: constellation lines under the capsules — labelled while fully clear.
    ctx.save()
    ctx.beginPath()
    ctx.rect(0, 0, this.bounds.width, this.bounds.height)
    for (const box of blocking) ctx.rect(box.x, box.y, box.w, box.h)
    ctx.clip('evenodd')
    this.drawEdges(dy)
    for (const leaving of this.exiting) this.drawSprite(leaving.sprite.ghost, leaving.sprite, leaving.node, dy, leaving.alpha)
    for (const node of this.nodes) {
      const sprite = this.ensureSprite(node)
      const fade = this.alpha.get(node.id) ?? 1, label = this.labelAlpha.get(node.id) ?? 0
      if (label < 1) this.drawSprite(sprite.ghost, sprite, node, dy, fade * (1 - label))
      if (label > 0) this.drawSprite(sprite.image, sprite, node, dy, fade * label)
    }
    ctx.restore()
    // Keep-clear zones (drop zone, composer): nothing at all behind them.
    for (const box of this.surfaces) if (box.kind === 'clear') ctx.clearRect(box.x - 1, box.y - 1, box.w + 2, box.h + 2)
    ctx.globalAlpha = 1
  }

  private drawSprite(image: HTMLCanvasElement, sprite: Sprite, node: GraphNode, dy: number, alpha: number): void {
    const a = alpha * DEPTH_ALPHA[node.depth]
    if (a <= 0.003) return
    const x = node.x - sprite.width / 2, y = node.y + dy - sprite.height / 2
    if (x > this.bounds.width || y > this.bounds.height || x + sprite.width < 0 || y + sprite.height < 0) return   // culled
    this.ctx!.globalAlpha = Math.min(1, a)
    this.ctx!.drawImage(image, x, y, sprite.width, sprite.height)
  }

  // A gradient from one hue to another along the unit segment (0,0)→(1,0), cached per hue
  // pair; each line is drawn by transforming that unit segment onto the trimmed line, so no
  // gradient is allocated per edge per frame.
  private gradient(from: number, to: number, colour: (index: number) => [number, number, number]): CanvasGradient {
    const key = `${from}-${to}`
    let gradient = this.gradients.get(key)
    if (!gradient) {
      const [r1, g1, b1] = colour(from), [r2, g2, b2] = colour(to)
      gradient = this.ctx!.createLinearGradient(0, 0, 1, 0)
      gradient.addColorStop(0, `rgb(${r1}, ${g1}, ${b1})`)
      gradient.addColorStop(1, `rgb(${r2}, ${g2}, ${b2})`)
      this.gradients.set(key, gradient)
    }
    return gradient
  }

  // Lines end at the capsule outlines (exact pill geometry): never across a label.
  private drawEdges(dy: number): void {
    const ctx = this.ctx!
    const byId = new Map(this.nodes.map((node) => [node.id, node]))
    const pulse = this.scene.mode === 'resume' && this.scene.resumeProcessing ? 0.8 + 0.2 * Math.sin(this.simTime * 2.4) : 1   // only while a real analysis runs
    const colour = (index: number): [number, number, number] => (index === 3 ? GAP_HUE : HUES[index])
    let count = 0
    for (const [key, alpha] of this.edgeAlphas) {
      if (alpha <= 0.004) continue
      const [ia, ib] = key.split('\u0000')
      const a = byId.get(ia), b = byId.get(ib)
      if (!a || !b) continue
      const segment = trimToCapsules({ x: a.x, y: a.y + dy, w: a.w, h: a.h }, { x: b.x, y: b.y + dy, w: b.w, h: b.h })
      if (!segment) continue
      const length = Math.hypot(segment.x1 - segment.x0, segment.y1 - segment.y0)
      const cos = (segment.x1 - segment.x0) / length, sin = (segment.y1 - segment.y0) / length
      const fade = Math.min(this.alpha.get(a.id) ?? 1, this.alpha.get(b.id) ?? 1) * Math.min(DEPTH_ALPHA[a.depth], DEPTH_ALPHA[b.depth])
      ctx.globalAlpha = alpha * fade * pulse
      ctx.strokeStyle = this.gradient(this.gapIds.has(a.id) ? 3 : a.hue, this.gapIds.has(b.id) ? 3 : b.hue, colour)
      const d = this.dpr
      ctx.setTransform(d * cos * length, d * sin * length, -d * sin * length, d * cos * length, d * segment.x0, d * segment.y0)
      ctx.lineWidth = 1 / length   // 1 CSS px after the uniform scale
      ctx.beginPath()
      ctx.moveTo(0, 0)
      ctx.lineTo(1, 0)
      ctx.stroke()
      count++
    }
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    this.setEdgeCount(count)
  }

  private setEdgeCount(count: number): void {
    const value = String(count)
    if (this.canvas.dataset.edgeCount !== value) this.canvas.dataset.edgeCount = value
  }

  // One batch of layout reads, only after the foreground layout changed: the outermost
  // foreground surfaces, the keep-clear zones and the route's anchor surface.
  private readOccluders(): void {
    this.occludersDirty = false
    const surfaces: Surface[] = []
    const visible = (rect: DOMRect) => rect.width >= 1 && rect.height >= 1 && rect.bottom >= 0 && rect.top <= this.bounds.height && rect.right >= 0 && rect.left <= this.bounds.width
    for (const element of Array.from(document.querySelectorAll<HTMLElement>(OCCLUDER_SELECTOR))) {
      if (element.parentElement?.closest(OCCLUDER_SELECTOR)) continue   // outermost surfaces only
      let rect = element.getBoundingClientRect()
      if (!visible(rect)) continue
      if (element.matches(TEXT_BLOCK_SELECTOR)) {
        const range = document.createRange()
        range.selectNodeContents(element)
        const text = range.getBoundingClientRect()
        if (text.width >= 1 && text.height >= 1) rect = new DOMRect(text.left - TEXT_PAD, text.top - TEXT_PAD, text.width + TEXT_PAD * 2, text.height + TEXT_PAD * 2)
      }
      surfaces.push({ x: rect.left, y: rect.top, w: rect.width, h: rect.height, kind: element.matches(GLASS_SELECTOR) ? 'glass' : 'solid' })
    }
    for (const element of Array.from(document.querySelectorAll<HTMLElement>(KEEP_CLEAR_SELECTOR))) {
      const rect = element.getBoundingClientRect()
      if (visible(rect)) surfaces.push({ x: rect.left, y: rect.top, w: rect.width, h: rect.height, kind: 'clear' })
    }
    const anchor = document.querySelector<HTMLElement>(ANCHOR_SELECTOR)?.getBoundingClientRect()
    this.anchor = anchor && anchor.width >= 1 && anchor.height >= 1 ? { x: anchor.left, y: anchor.top, w: anchor.width, h: anchor.height } : null
    this.surfaces = surfaces
  }

  private readonly onLayoutChange = (): void => {
    this.occludersDirty = true
    this.scheduleLayoutSettle()
    if (this.mode === 'off' || this.running) return                // running loop redraws anyway
    if (document.hidden) { this.redrawOnVisible = true; return }   // hidden: redraw on return
    requestTick(REDRAW_TICK, () => this.draw())                    // sleeping/static: one redraw
  }

  // Once the foreground layout has been still for LAYOUT_SETTLE_MS (data loaded, scrolling
  // stopped), the formation is re-placed into the open space that now exists. A timer reset
  // by each change — not a polling loop.
  private scheduleLayoutSettle(): void {
    if (this.mode === 'off' || this.destroyed) return
    if (this.layoutTimer) clearTimeout(this.layoutTimer)
    this.layoutTimer = setTimeout(this.onLayoutSettled, LAYOUT_SETTLE_MS)
  }

  private readonly onLayoutSettled = (): void => {
    this.layoutTimer = null
    if (this.destroyed || this.mode === 'off') return
    if (document.hidden) { this.placeOnVisible = true; return }
    this.readOccluders()
    if (this.mode === 'static') { this.layoutStatic(); return }
    this.assignSlots()
    this.wake(false)
  }

  // The shared scroll feed: surfaces moved, and (animated only) a new parallax goal. Scroll
  // wakes the loop without counting as activity, so the drift does not restart.
  private readonly onScroll = (): void => {
    if (this.mode !== 'animated') { this.onLayoutChange(); return }
    const scrollY = Math.max(0, window.scrollY || 0)
    this.parallaxTarget = scrollY > 0 ? -Math.min(PARALLAX.max, scrollY * PARALLAX.factor) : 0
    this.occludersDirty = true
    this.scheduleLayoutSettle()
    if (this.running) return
    if (document.hidden) { this.redrawOnVisible = true; return }
    if (this.parallaxTarget !== this.parallax) this.wake(false)
    else requestTick(REDRAW_TICK, () => this.draw())
  }

  // --- events --------------------------------------------------------------------------------
  private readonly onPointer = (): void => {
    if (this.mode !== 'animated' || document.hidden) return
    const sample = pointerFeed.latest
    if (!sample.inside) { if (this.magnetWeight > 0 || this.pointer.speed > 0) this.wake(false); return }
    // Wake only when the pointer comes near a capsule, or a hovered interactive card is
    // involved — moving over the UI elsewhere costs nothing.
    this.pointer.active = true; this.pointer.x = sample.x; this.pointer.y = sample.y - this.parallax
    if (this.pointerNear()) this.wake()
    else if (pointerFeed.magnet || this.magnetWeight > 0) this.wake(false)
  }

  private readonly onResize = (): void => {
    if (!this.ctx || this.destroyed) return
    const widthBefore = this.bounds.width
    this.measure()
    this.occludersDirty = true
    const crossed = (widthBefore < SKILL_GRAPH_LIMITS.mobileWidth) !== this.small()
    if (crossed) { this.labels = []; this.nodes = []; this.exiting = []; this.rebuild(); return }   // capsule size/cap change
    for (const node of this.nodes) step([node], 1e-6, this.simTime, this.bounds, { active: false, x: 0, y: 0, speed: 0 }, this.config, false)
    this.exiting = []
    if (this.mode === 'static') { this.layoutStatic(); return }
    this.assignSlots()
    this.draw()
    if (this.mode === 'animated') this.wake()
  }

  private readonly onVisibility = (): void => {
    if (document.hidden) { if (this.running) this.stop('paused'); return }
    const redraw = this.redrawOnVisible || this.occludersDirty
    this.redrawOnVisible = false
    if (this.placeOnVisible) { this.placeOnVisible = false; this.scheduleLayoutSettle() }
    if (this.mode === 'animated') { this.wake(); return }
    if (this.mode === 'static' && redraw) requestTick(REDRAW_TICK, () => this.draw())
  }

  private setData(state: Mode, loop: string, reason = ''): void {
    this.canvas.dataset.state = state
    this.canvas.dataset.loop = loop
    this.canvas.dataset.nodeCount = String(state === 'off' ? 0 : this.nodes.length)
    if (reason) this.canvas.dataset.reason = reason; else delete this.canvas.dataset.reason
  }
}
