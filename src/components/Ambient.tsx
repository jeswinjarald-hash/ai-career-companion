import { useRef } from 'react'
import { usePointerLight } from './usePointerLight'
import { SkillGraphCanvas } from './SkillGraphCanvas'

// Decorative ambient light behind every screen. Layer order (back to front): base gradient
// and grid, three slowly drifting glows, the skill graph canvas (real skills only), then two
// pointer-following spotlights (blue-violet primary, trailing teal secondary).
// aria-hidden, pointer-events: none and z-index 0 (styles in src/theme.css), so it never
// takes input or focus. Orbs animate only `transform` and stop under reduced motion; the
// spotlights run only for a mouse/trackpad without reduced motion (see usePointerLight).
// data-tracking / data-pointer describe the live state (also used by the e2e tests).
export function Ambient() {
  const rootRef = useRef<HTMLDivElement>(null)
  const primaryRef = useRef<HTMLSpanElement>(null)
  const secondaryRef = useRef<HTMLSpanElement>(null)
  usePointerLight(rootRef, primaryRef, secondaryRef)
  return <div className="ambient" aria-hidden="true" ref={rootRef} data-tracking="off" data-pointer="out">
    <span className="ambient-orb blue" />
    <span className="ambient-orb orchid" />
    <span className="ambient-orb teal" />
    <SkillGraphCanvas />
    <span className="ambient-spot primary" ref={primaryRef} />
    <span className="ambient-spot secondary" ref={secondaryRef} />
  </div>
}
