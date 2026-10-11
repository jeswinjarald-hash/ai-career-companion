import type { Page } from '@playwright/test'

// The skill graph engine's read-only dev snapshot (SkillGraphEngine.snapshot(), exposed as
// window.__skillGraph only in dev builds), shared by the skill-graph specs.
export type GraphNodeView = { id: string; label: string; x: number; y: number; vx: number; vy: number; w: number; h: number; depth: number; gap: boolean; alpha: number; labelAlpha: number; placedOpen: boolean }
export type Snapshot = {
  mode: string; running: boolean; bounds: { width: number; height: number }; dpr: number
  scene: string; params: { formation: number; drift: number; linkRadius: number; linkAlpha: number; linksPerNode: number }
  transition: number | null; parallax: number; magnetWeight: number
  nodes: GraphNodeView[]; targets: Array<{ x: number; y: number } | null> | null
  edges: Array<{ a: string; b: string; alpha: number; distance: number | null }>
  surfaces: number; signals: Record<string, number | boolean> | null; anchor: { x: number; y: number; w: number; h: number } | null
}
declare global { interface Window { __skillGraph?: { snapshot(): Snapshot } } }
export const snapshot = (page: Page) => page.evaluate(() => window.__skillGraph?.snapshot() ?? null) as Promise<Snapshot>
