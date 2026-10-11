import { useEffect, useState } from 'react'
import { EmptyState, PageHeading } from '../components/common'
import { errorText } from '../lib/errorText'
import { getJobMatches, type JobMatchResult } from '../services/resumeService'

type TopMatch = { status: 'idle' } | { status: 'loading' } | { status: 'ready'; top: JobMatchResult | null } | { status: 'error'; message: string }

export function RoadmapView({ resumeId }: { resumeId: number | null }) {
  const [topMatch, setTopMatch] = useState<TopMatch>({ status: 'idle' })
  const [reload, setReload] = useState(0)

  // The context always belongs to the current resume: it is cleared as soon as the
  // resume changes, and a response for a previous resume (or an unmounted page) is ignored.
  useEffect(() => {
    let cancelled = false
    if (resumeId === null) { setTopMatch({ status: 'idle' }); return }
    setTopMatch({ status: 'loading' })
    getJobMatches(resumeId, 1)
      .then((matches) => { if (!cancelled) setTopMatch({ status: 'ready', top: matches[0] ?? null }) })
      .catch((reason: unknown) => { if (!cancelled) setTopMatch({ status: 'error', message: errorText(reason, 'We could not load your top job match.') }) })
    return () => { cancelled = true }
  }, [resumeId, reload])

  return <>
    <PageHeading eyebrow="Learning Roadmap" title="A path from gaps to capability." lede="Personalized roadmap generation is not part of this release." />
    <EmptyState title="Not available yet" message="A generated learning roadmap is not implemented in this version, so nothing is shown here rather than a placeholder plan. Skill Gap Analysis already gives a prioritized improvement plan for any opportunity you select." />
    {topMatch.status === 'loading' && <p className="muted" role="status">Loading the skill gap context from your top job match...</p>}
    {topMatch.status === 'error' && <div className="error-notice" role="alert">{topMatch.message} <button className="text-button" onClick={() => setReload((value) => value + 1)}>Retry</button></div>}
    {topMatch.status === 'ready' && topMatch.top && <section className="card comparison-card" aria-labelledby="roadmap-gap-context">
      <div className="card-heading"><div><p className="eyebrow">CURRENT SKILL GAP CONTEXT</p><h3 id="roadmap-gap-context">From your top job match: {topMatch.top.job_title}, {topMatch.top.company}</h3></div></div>
      {topMatch.top.missing_required_skills.length > 0
        ? <div className="chip-list">{topMatch.top.missing_required_skills.map((skill) => <span className="warning-chip" key={skill}>{skill}</span>)}</div>
        : <p className="muted">Your resume covers every required skill listed for this opportunity.</p>}
    </section>}
  </>
}
