import { useEffect, useRef, useState } from 'react'
import { PageHeading } from '../components/common'
import { TrackJobButton } from '../components/applications/ApplicationWidgets'
import { getJobDetails, type JobPosting } from '../services/jobService'
import { errorText } from '../lib/errorText'
import { MATCH_SCORE_DEFINITION } from '../lib/insights'
import { ScoreRing } from '../components/charts'
import { getJobMatches, type JobMatchResult } from '../services/resumeService'

// The backend scores only the opportunities it first retrieves as semantically closest to
// the resume (at most 20 per request), so a job outside that set has no score at all —
// which is different from a score of zero, and is shown as such.
const MATCH_RETRIEVAL_LIMIT = 20
type MatchState =
  | { kind: 'not-checked' }
  | { kind: 'checking' }
  | { kind: 'scored'; result: JobMatchResult }
  | { kind: 'not-retrieved'; retrieved: number }
  | { kind: 'error'; message: string }

export function JobDetailsView({ jobId, resumeId, onBack, onAnalyzeSkillGap, onCustomizeApplication, onInterviewPrep, onOpenApplication }: { jobId: string | null; resumeId: number | null; onBack: () => void; onAnalyzeSkillGap: () => void; onCustomizeApplication: () => void; onInterviewPrep: () => void; onOpenApplication: (applicationId: number) => void }) {
  const [job, setJob] = useState<JobPosting | null>(null)
  const [jobError, setJobError] = useState('')
  const [loading, setLoading] = useState(true)
  const [match, setMatch] = useState<MatchState>({ kind: 'not-checked' })
  // Identifies the latest match request, so a response for a previously shown job or
  // resume can never be displayed under the current one.
  const matchRequest = useRef(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setJobError(''); setJob(null)
    if (!jobId) { setLoading(false); setJobError('No job was selected.'); return }
    void getJobDetails(jobId).then((result) => { if (!cancelled) { setJob(result); setLoading(false) } }).catch((error: unknown) => { if (!cancelled) { setJobError(errorText(error, 'We could not load this job.')); setLoading(false) } })
    return () => { cancelled = true }
  }, [jobId])

  useEffect(() => { matchRequest.current += 1; setMatch({ kind: 'not-checked' }) }, [jobId, resumeId])

  const loadMatch = async () => {
    if (!jobId || resumeId === null || match.kind === 'checking') return
    const request = ++matchRequest.current
    setMatch({ kind: 'checking' })
    try {
      const results = await getJobMatches(resumeId, MATCH_RETRIEVAL_LIMIT)
      if (request !== matchRequest.current) return
      const result = results.find((item) => item.job_id === jobId)
      setMatch(result ? { kind: 'scored', result } : { kind: 'not-retrieved', retrieved: results.length })
    } catch (error: unknown) {
      if (request === matchRequest.current) setMatch({ kind: 'error', message: errorText(error, 'We could not load your match result.') })
    }
  }

  if (loading) return <PageHeading eyebrow="Opportunity" title="Loading opportunity..." lede="" />
  if (jobError || !job) return <><PageHeading eyebrow="Opportunity" title="Opportunity not available." lede={jobError || 'This opportunity could not be loaded.'} action={<button className="text-button" onClick={onBack}>Back to search →</button>} /></>

  const matchResult = match.kind === 'scored' ? match.result : null

  return <>
    <PageHeading eyebrow="Opportunity" title={job.job_title} lede={<><span className="opportunity-type-chip inline">{job.employment_type}</span> {job.company} · {job.domain}</>} action={<div className="heading-actions"><TrackJobButton jobId={job.job_id} onOpenApplication={onOpenApplication} /><button className="text-button" onClick={onBack}>Back to search →</button></div>} />
    <section className="results-grid resume-result-grid">
      <article className="card result-card"><p className="eyebrow">OVERVIEW</p><dl className="fact-list"><dt>Location</dt><dd>{job.location}</dd><dt>Work mode</dt><dd>{job.work_mode}</dd><dt>Employment type</dt><dd>{job.employment_type}</dd><dt>Posted</dt><dd>{job.posted_date}</dd></dl></article>
      <article className="card result-card"><p className="eyebrow">DESCRIPTION</p><p className="body-text">{job.job_description}</p></article>
      <article className="card result-card"><p className="eyebrow">RESPONSIBILITIES</p><ul className="result-items">{job.responsibilities.map((item, index) => <li key={index}>{item}</li>)}</ul></article>
      <article className="card result-card"><p className="eyebrow">REQUIRED SKILLS</p><div className="chip-list">{job.required_skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div>{job.preferred_skills.length > 0 && <><p className="muted result-gap-label">Preferred</p><div className="chip-list">{job.preferred_skills.map((skill) => <span key={skill}>{skill}</span>)}</div></>}</article>
      <article className="card result-card"><p className="eyebrow">QUALIFICATIONS</p><ul className="result-items">{job.qualifications.map((item, index) => <li key={index}>{item}</li>)}</ul><p className="muted">Experience: {job.experience_requirements}</p><p className="muted">Education: {job.education_requirements}</p></article>
    </section>
    <section className="card comparison-card">
      <div className="card-heading"><div><p className="eyebrow">RESUME MATCH</p><h3>Your match for this role</h3></div>{resumeId !== null && (match.kind === 'not-checked' || match.kind === 'checking') && <button className="primary-button" onClick={() => void loadMatch()} disabled={match.kind === 'checking'}>{match.kind === 'checking' ? 'Checking...' : 'Check my match'}</button>}</div>
      {resumeId === null && <div className="architecture-note">Process a resume to see your match for this role.</div>}
      {match.kind === 'error' && <div className="error-notice" role="alert">{match.message} <button className="text-button" onClick={() => void loadMatch()}>Retry</button></div>}
      {matchResult && <div className="results-grid resume-result-grid"><article className="card result-card"><p className="eyebrow">MATCH SCORE</p><ScoreRing value={matchResult.match_score} label="Match score" caption="match" /><p className="result-bullet">{matchResult.reasoning}</p><p className="muted">{MATCH_SCORE_DEFINITION}</p></article><article className="card result-card"><p className="eyebrow">MATCHED SKILLS</p>{matchResult.matched_required_skills.length > 0 ? <div className="chip-list">{matchResult.matched_required_skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div> : <p className="muted">None</p>}</article><article className="card result-card"><p className="eyebrow">MISSING REQUIRED SKILLS</p>{matchResult.missing_required_skills.length > 0 ? <div className="chip-list">{matchResult.missing_required_skills.map((skill) => <span className="warning-chip" key={skill}>{skill}</span>)}</div> : <p className="muted">None</p>}</article></div>}
      {match.kind === 'not-retrieved' && <div className="architecture-note" role="status"><div><strong>No match score for this opportunity</strong><p>Match scores are calculated only for the {match.retrieved} opportunities retrieved as closest to your resume, and this one is not among them. This is not a score of zero. Skill Gap Analysis still compares it with your resume requirement by requirement.</p></div></div>}
      {resumeId !== null && <div className="detail-actions"><button className="primary-button" onClick={onAnalyzeSkillGap}>Analyze Skill Gaps →</button><button className="secondary-button" onClick={onCustomizeApplication}>Customize Application →</button><button className="secondary-button" onClick={onInterviewPrep}>Prepare for Interview →</button></div>}
    </section>
  </>
}
