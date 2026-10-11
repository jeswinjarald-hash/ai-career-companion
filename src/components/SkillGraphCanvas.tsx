import { useEffect, useRef, useSyncExternalStore } from 'react'
import { getScene, getSkills, subscribeScene, subscribeSkills } from './backgroundRuntime'
import { SkillGraphEngine } from './skillGraphEngine'

declare global {
  interface Window { __skillGraph?: SkillGraphEngine }
}

// Decorative layer of the user's real skills as floating capsules (see skillGraphEngine.ts).
// aria-hidden, pointer-events: none, inside the fixed ambient background: never focusable,
// never a click target, never the only place skills are shown (Resume Studio lists them).
// React re-renders this only when the published skill list or route scene changes; animation
// runs outside React. The engine is created once per mount (route changes only call
// setScene) and fully torn down on unmount (Strict Mode mount → unmount → mount leaves
// exactly one live engine).
export function SkillGraphCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const engineRef = useRef<SkillGraphEngine | null>(null)
  const skills = useSyncExternalStore(subscribeSkills, getSkills)
  const scene = useSyncExternalStore(subscribeScene, getScene)

  useEffect(() => {
    if (!canvasRef.current) return
    const engine = new SkillGraphEngine(canvasRef.current)
    engineRef.current = engine
    engine.setScene(getScene())
    engine.setSkills(getSkills())
    if (import.meta.env.DEV) window.__skillGraph = engine
    return () => {
      engine.destroy()
      engineRef.current = null
      if (import.meta.env.DEV && window.__skillGraph === engine) delete window.__skillGraph
    }
  }, [])

  useEffect(() => { engineRef.current?.setSkills(skills) }, [skills])
  useEffect(() => { engineRef.current?.setScene(scene) }, [scene])

  return <canvas ref={canvasRef} className="skill-graph" aria-hidden="true" data-state="off" data-loop="stopped" data-node-count="0" />
}
