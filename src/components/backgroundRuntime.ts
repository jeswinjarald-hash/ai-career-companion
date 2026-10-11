// Shared runtime for the decorative background (ambient spotlight + skill graph).
//
// frame scheduler — every background subsystem asks for its next tick here; all requests
//   made before a frame are served by ONE requestAnimationFrame, so pointer bursts and two
//   subsystems still cost a single frame.
// pointer feed — the latest mouse sample, written by the single pointer listener in
//   usePointerLight and read by the skill graph during its own tick (no second listener);
//   also the hovered interactive card ([data-graph-magnet]) that usePointerLight already
//   hit-tests, as a viewport rect.
// scroll feed — ONE passive, capturing scroll listener shared by every background subsystem
//   (installed while anyone subscribes); subscribers only mark work for their next tick.
// skills store / scene store — the real skill labels and the route scene (mode plus real
//   request states and skill-gap labels) that the app publishes for the graph; consumed with
//   useSyncExternalStore, so React re-renders only when they actually change.
import { DEFAULT_SCENE, type SceneContext } from '../lib/skillGraphScene'
import type { Rect } from '../lib/skillGraphPhysics'

type Tick = (time: number) => void
const pending = new Map<string, Tick>()
let frame = 0

const runFrame = (time: number) => {
  frame = 0
  const ticks = Array.from(pending.values())
  pending.clear()
  for (const tick of ticks) tick(time)
}

export function requestTick(key: string, tick: Tick): void {
  pending.set(key, tick)
  if (!frame) frame = window.requestAnimationFrame(runFrame)
}

export function cancelTick(key: string): void {
  pending.delete(key)
  if (pending.size === 0 && frame) { window.cancelAnimationFrame(frame); frame = 0 }
}

// --- pointer feed ---------------------------------------------------------------------------
export type PointerSample = { x: number; y: number; time: number; inside: boolean }
// `magnetElement` lets the graph drop a magnet whose card was unmounted (route change) while
// the pointer rested on it — no stale reference keeps attracting.
export const pointerFeed: { latest: PointerSample; magnet: Rect | null; magnetElement: Element | null; listeners: Set<() => void> } = {
  latest: { x: 0, y: 0, time: 0, inside: false },
  magnet: null,
  magnetElement: null,
  listeners: new Set(),
}
export function publishPointer(sample: PointerSample): void {
  pointerFeed.latest = sample
  for (const listener of pointerFeed.listeners) listener()
}
export function publishMagnet(rect: Rect | null, element: Element | null = null): void {
  const current = pointerFeed.magnet
  pointerFeed.magnetElement = rect ? element : null
  if (current === rect || (current && rect && current.x === rect.x && current.y === rect.y && current.w === rect.w && current.h === rect.h)) return
  pointerFeed.magnet = rect
  for (const listener of pointerFeed.listeners) listener()
}
export function subscribePointer(listener: () => void): () => void {
  pointerFeed.listeners.add(listener)
  return () => { pointerFeed.listeners.delete(listener) }
}

// --- scroll feed -----------------------------------------------------------------------------
const scrollListeners = new Set<() => void>()
const onScroll = () => { for (const listener of scrollListeners) listener() }
export function subscribeScroll(listener: () => void): () => void {
  if (scrollListeners.size === 0) window.addEventListener('scroll', onScroll, { passive: true, capture: true })
  scrollListeners.add(listener)
  return () => {
    scrollListeners.delete(listener)
    if (scrollListeners.size === 0) window.removeEventListener('scroll', onScroll, { capture: true })
  }
}

// --- skills store ----------------------------------------------------------------------------
let skills: readonly string[] = []
const skillListeners = new Set<() => void>()
export function publishSkills(next: readonly string[]): void {
  if (next.length === skills.length && next.every((label, index) => label === skills[index])) return
  skills = next
  for (const listener of skillListeners) listener()
}
export const getSkills = (): readonly string[] => skills
export function subscribeSkills(listener: () => void): () => void {
  skillListeners.add(listener)
  return () => { skillListeners.delete(listener) }
}

// --- scene store -----------------------------------------------------------------------------
let scene: SceneContext = DEFAULT_SCENE
const sceneListeners = new Set<() => void>()
const sameLabels = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((label, index) => label === b[index])
export function publishScene(patch: Partial<SceneContext>): void {
  const next = { ...scene, ...patch }
  if (next.mode === scene.mode && next.resumeProcessing === scene.resumeProcessing && next.assistantPending === scene.assistantPending && sameLabels(next.gapSkills, scene.gapSkills)) return
  scene = next
  for (const listener of sceneListeners) listener()
}
export const getScene = (): SceneContext => scene
export function subscribeScene(listener: () => void): () => void {
  sceneListeners.add(listener)
  return () => { sceneListeners.delete(listener) }
}
