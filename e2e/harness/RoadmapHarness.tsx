import { useEffect, useState } from 'react'
import { RoadmapView } from '../../src/views/RoadmapView'

// Test seam for e2e/roadmap-lifecycle.spec.ts: mounts the real RoadmapView (real service
// calls to the isolated backend, same credentials) and lets a test change `resumeId`
// while the view stays mounted — a transition the app's own screens cannot produce on
// demand, but which the view must handle without showing another resume's data.
declare global {
  interface Window { roadmapHarness?: { setResumeId: (id: number | null) => void } }
}

export function RoadmapHarness() {
  const [resumeId, setResumeId] = useState<number | null>(null)
  useEffect(() => { window.roadmapHarness = { setResumeId } }, [])
  return <main id="main-content" data-resume-id={resumeId ?? ''}><RoadmapView resumeId={resumeId} /></main>
}
