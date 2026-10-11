import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { PageHeading } from '../components/common'
import { ScoreRing } from '../components/charts'
import { Icon, type IconName } from '../components/icons'
import { ApplicationActivity } from '../components/applications/ApplicationWidgets'
import { formatDateTime } from '../components/applications/applicationFormat'
import { MATCH_SCORE_DEFINITION, dashboardState, resumeCoverage, type DashboardStateKind, type ResumeLifecycle } from '../lib/insights'
import { errorText } from '../lib/errorText'
import { profileCompletion } from '../lib/profileCompletion'
import type { View } from '../routing'
import type { AuthUser } from '../services/authService'
import type { CandidateProfile } from '../services/profileService'
import { getJobMatches, type JobMatchResult, type ResumeRecord, type StructuredResume } from '../services/resumeService'

const TOP_MATCH_COUNT = 5

const greetingForTime = () => { const hour = new Date().getHours(); return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening' }

type Props = {
  currentUser: AuthUser | null
  profile: CandidateProfile | null
  resumeLifecycle: ResumeLifecycle
  resumeRestoring: boolean
  resumeRecord: ResumeRecord | null
  structuredResume: StructuredResume | null
  processingLabel: string | null
  notice: string
  loadError: string
  onRetryLoad: () => void
  onNavigate: (view: View) => void
  onOpenApplication: (applicationId: number) => void
  onOpenJob: (jobId: string) => void
  onReprocess: () => void
}

export function DashboardView(props: Props) {
  const { currentUser, profile, resumeRecord, structuredResume, onNavigate } = props
  const state = dashboardState({ restoring: props.resumeRestoring, loadError: props.loadError, lifecycle: props.resumeLifecycle, structured: structuredResume })
  const firstName = (currentUser?.full_name ?? '').trim().split(/\s+/)[0] || 'there'
  const analysed = state === 'ready' || state === 'stale'
  const data = analysed ? structuredResume?.data : undefined
  const resumeId = analysed && resumeRecord ? resumeRecord.id : null

  return <>
    <PageHeading eyebrow="Overview" title={`Good ${greetingForTime()}, ${firstName}.`} lede={LEDE[state]} action={primaryAction(state, onNavigate)} />
    <StateBanner {...props} state={state} />
    {state === 'loading' || state === 'load_error' ? null : analysed && data ? <div className="dash-grid">
      <div className="dash-col">
        <TopMatches resumeId={resumeId} onOpenJob={props.onOpenJob} onSeeAll={() => onNavigate('careers')} />
        <ResumeCoverage data={data} onOpenResults={() => onNavigate('resume-results')} />
      </div>
      <div className="dash-col">
        <ProfileCompleteness profile={profile} onOpenProfile={() => onNavigate('profile')} />
        {data.skills.length > 0 && <section className="card module" aria-labelledby="dash-skills">
          <div className="module-header"><div><p className="eyebrow">From your resume</p><h2 id="dash-skills">Skills identified</h2></div><button className="text-button" onClick={() => onNavigate('resume-results')}>All results</button></div>
          <div className="chip-list">{data.skills.slice(0, 14).map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div>
          {data.skills.length > 14 && <p className="muted">+ {data.skills.length - 14} more in your resume results.</p>}
        </section>}
        <ApplicationActivity onOpenTracker={() => onNavigate('applications')} onOpenApplication={props.onOpenApplication} />
      </div>
    </div> : <div className="dash-grid">
      <div className="dash-col">
        <section className="card module" aria-labelledby="dash-how">
          <div className="module-header"><div><p className="eyebrow">How it works</p><h2 id="dash-how">From resume to next step</h2></div></div>
          <ol className="steps-list">
            <li><div><strong>Upload your resume</strong><span>PDF or DOCX, up to 10 MB. Text-based files work best; scanned images cannot be read.</span></div></li>
            <li><div><strong>Review what was extracted</strong><span>Skills, education, experience and projects found in your file — check them against your resume.</span></div></li>
            <li><div><strong>Explore matches and skill gaps</strong><span>Opportunities ranked against your resume, with requirement-by-requirement gap analysis.</span></div></li>
          </ol>
        </section>
      </div>
      <div className="dash-col">
        <ProfileCompleteness profile={profile} onOpenProfile={() => onNavigate('profile')} />
        <ApplicationActivity onOpenTracker={() => onNavigate('applications')} onOpenApplication={props.onOpenApplication} />
      </div>
    </div>}
  </>
}

const LEDE: Record<DashboardStateKind, string> = {
  loading: 'Loading your workspace…',
  load_error: 'Your resume status could not be loaded.',
  no_resume: 'Start by uploading your resume — everything here is built from it.',
  awaiting_analysis: 'Your resume is uploaded but has not been analysed yet.',
  processing: 'Your resume is being analysed.',
  failed: 'We could not finish analysing your resume.',
  stale: 'Your results come from an earlier version of the resume parser.',
  ready: 'Your career workspace, built from your latest analysed resume.',
}

function primaryAction(state: DashboardStateKind, onNavigate: (view: View) => void): ReactNode {
  if (state === 'loading' || state === 'load_error') return undefined
  if (state === 'no_resume') return <button className="primary-button" onClick={() => onNavigate('resume')}><Icon name="upload" className="nav-icon" />Upload resume</button>
  if (state === 'ready') return <button className="primary-button" onClick={() => onNavigate('careers')}>Explore opportunities</button>
  return <button className="secondary-button" onClick={() => onNavigate('resume')}>Open Resume Studio</button>
}

function StateBanner({ state, resumeRecord, structuredResume, processingLabel, notice, loadError, onRetryLoad, onNavigate, onReprocess }: Props & { state: DashboardStateKind }) {
  const file = resumeRecord?.original_filename ?? 'your resume'
  const banner = (tone: '' | 'success' | 'warning' | 'danger', icon: IconName | 'spinner', title: ReactNode, body: ReactNode, actions?: ReactNode, live: 'status' | 'alert' = 'status') =>
    <section className={`card state-banner ${tone}`} role={live} aria-label="Resume status">
      <span className="state-banner-icon">{icon === 'spinner' ? <span className="spinner" aria-hidden="true" /> : <Icon name={icon} />}</span>
      <div><h2>{title}</h2><p>{body}</p></div>
      {actions && <div className="state-banner-actions">{actions}</div>}
    </section>

  switch (state) {
    case 'loading': return banner('', 'spinner', 'Loading your resume status…', 'Checking for your most recently uploaded resume.')
    case 'load_error': return banner('danger', 'alert', 'Couldn’t load your resume status', loadError,
      <button className="primary-button" onClick={onRetryLoad}>Try again</button>, 'alert')
    case 'no_resume': return banner('', 'upload', 'No resume uploaded yet', 'Nothing has been analysed, so there are no extracted skills or opportunity matches to show.',
      <button className="secondary-button" onClick={() => onNavigate('resume')}>Go to Resume Studio</button>)
    case 'awaiting_analysis': return banner('warning', 'clock', <>Awaiting analysis <span className="status-chip warning">Not analysed</span></>,
      <>{file} was uploaded{resumeRecord ? ` ${formatDateTime(resumeRecord.created_at)}` : ''}, but its analysis did not finish. Your file is stored, so it can be analysed now.</>,
      <><button className="primary-button" onClick={onReprocess}>Analyse now</button><button className="secondary-button" onClick={() => onNavigate('resume')}>Upload a different file</button></>)
    case 'processing': return banner('', 'spinner', <>Analysing {file} <span className="status-chip info">In progress</span></>,
      <>Current step: {processingLabel ?? 'processing'}. Results appear here when the server confirms each step.</>,
      <button className="secondary-button" onClick={() => onNavigate('resume')}>View progress</button>)
    case 'failed': return banner('danger', 'alert', <>Analysis failed <span className="status-chip danger">Failed</span></>,
      <>{notice || `We could not analyse ${file}.`}</>,
      <>{resumeRecord && <button className="primary-button" onClick={onReprocess}>Retry analysis</button>}<button className="secondary-button" onClick={() => onNavigate('resume')}>Upload a different file</button></>, 'alert')
    case 'stale': return banner('warning', 'refresh', <>Results may be outdated <span className="status-chip warning">Earlier parser</span></>,
      <>{file} was analysed by an earlier version of the resume parser. Reprocess it to re-extract your stored file with the current parser.</>,
      <button className="primary-button" onClick={onReprocess}>Reprocess resume</button>)
    case 'ready': return banner('success', 'check', <>Resume analysed <span className="status-chip success">Current</span></>,
      <>{file}{structuredResume ? ` · analysed ${formatDateTime(structuredResume.updated_at)}` : ''}</>,
      <button className="secondary-button" onClick={() => onNavigate('resume-results')}>View analysis</button>)
  }
}

// Top opportunities for the current resume (GET /api/resumes/{id}/job-matches?top_k=5).
// Cleared as soon as the resume changes; a response for an earlier resume is ignored.
function TopMatches({ resumeId, onOpenJob, onSeeAll }: { resumeId: number | null; onOpenJob: (jobId: string) => void; onSeeAll: () => void }) {
  const [matches, setMatches] = useState<JobMatchResult[] | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let cancelled = false
    setMatches(null); setError('')
    if (resumeId === null) return
    getJobMatches(resumeId, TOP_MATCH_COUNT)
      .then((result) => { if (!cancelled) setMatches(result) })
      .catch((reason: unknown) => { if (!cancelled) setError(errorText(reason, 'We could not load your top matches.')) })
    return () => { cancelled = true }
  }, [resumeId, reload])

  return <section className="card module" aria-labelledby="dash-matches" aria-busy={matches === null && !error}>
    <div className="module-header">
      <div><p className="eyebrow">Opportunities</p><h2 id="dash-matches">Top matches for your resume</h2></div>
      <button className="text-button" onClick={onSeeAll}>See all</button>
    </div>
    {error ? <div className="error-notice" role="alert"><div>{error}</div><button className="text-button" onClick={() => setReload((value) => value + 1)}>Retry</button></div>
      : matches === null ? <p className="muted" role="status"><span className="spinner" aria-hidden="true" /> Ranking opportunities against your resume…</p>
      : matches.length === 0 ? <p className="muted">No opportunities in the current catalogue matched your resume. Try a search in Opportunities.</p>
      : <>
        <ol className="match-list">{matches.map((match) => {
          const requiredTotal = match.matched_required_skills.length + match.missing_required_skills.length
          return <li className="match-row" key={match.job_id}>
            <div>
              <button className="text-button" onClick={() => onOpenJob(match.job_id)}><strong>{match.job_title}</strong></button>
              <small>{match.company} · {match.employment_type}{requiredTotal > 0 ? ` · ${match.matched_required_skills.length} of ${requiredTotal} required skills` : ''}</small>
            </div>
            <div className="match-score"><b>{Math.round(match.match_score)}%</b><span>match</span></div>
          </li>
        })}</ol>
        <p className="muted">{MATCH_SCORE_DEFINITION}</p>
      </>}
  </section>
}

function ResumeCoverage({ data, onOpenResults }: { data: StructuredResume['data']; onOpenResults: () => void }) {
  const rows = resumeCoverage(data)
  const counted = rows.filter((row) => row.key !== 'summary')
  return <section className="card module" aria-labelledby="dash-coverage">
    <div className="module-header">
      <div><p className="eyebrow">Resume analysis</p><h2 id="dash-coverage">What was extracted</h2><p className="muted">{rows.filter((row) => row.found).length} of {rows.length} standard sections found in your file. A section counts as found when at least one entry was extracted from it.</p></div>
      <button className="text-button" onClick={onOpenResults}>Details</button>
    </div>
    <dl className="kpi-strip">{counted.slice(0, 4).map((row) => <div key={row.key}><dt>{row.label}</dt><dd>{row.count}</dd></div>)}</dl>
    <ul className="coverage-list" aria-label="Sections found in your resume">
      {rows.map((row) => <li key={row.key} className={row.found ? 'found' : 'absent'}>
        <Icon name={row.found ? 'check' : 'minus'} />{row.label}<span className="visually-hidden">{row.found ? ': found' : ': not found'}</span>
      </li>)}
    </ul>
  </section>
}

function ProfileCompleteness({ profile, onOpenProfile }: { profile: CandidateProfile | null; onOpenProfile: () => void }) {
  if (!profile) return null
  const completion = profileCompletion(profile)
  return <section className="card module" aria-labelledby="dash-profile">
    <div className="module-header"><div><p className="eyebrow">Career profile</p><h2 id="dash-profile">Profile details</h2></div><button className="text-button" onClick={onOpenProfile}>Edit</button></div>
    <div className="ring-row"><ScoreRing value={completion.percent} label="Profile details saved" size={88} /><div className="profile-score"><span>{completion.filled} of {completion.total} details saved</span></div></div>
    <p className="muted">{profile.target_roles.length > 0 ? `Target roles: ${profile.target_roles.join(', ')}` : 'Add target roles and skills so recommendations reflect where you want to go.'}</p>
  </section>
}
