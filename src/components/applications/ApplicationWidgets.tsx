import { useEffect, useState } from 'react'
import { Stat } from '../common'
import {
  ApplicationApiError, createApplicationFromJob, findApplicationForJob, updateApplication,
  type Application, type ApplicationReminder, type ApplicationSummary,
} from '../../services/applicationService'
import { REMINDER_LABEL, STATUS_LABEL, errorMessage, formatDate, formatDateTime, relativeDays } from './applicationFormat'
import { useApplicationOverview } from './useApplicationOverview'

export function ApplicationSummaryStats({ summary }: { summary: ApplicationSummary }) {
  return <section className="dashboard-stats tracker-stats" aria-label="Application summary">
    <Stat label="Total applications" value={String(summary.total_applications)} detail="Everything in your tracker" />
    <Stat label="Active" value={String(summary.active_applications)} detail="Not yet offer, rejected or withdrawn" />
    <Stat label="Upcoming deadlines" value={String(summary.upcoming_deadlines)} detail={`Not yet applied · due within ${summary.upcoming_deadline_window_days} days`} />
    <Stat label="Interviews scheduled" value={String(summary.interviews_scheduled)} detail="Upcoming interviews with a date set" />
    <Stat label="Offers received" value={String(summary.offers_received)} detail="Status: Offer Received" />
    <Stat label="Rejected" value={String(summary.rejected_applications)} detail="Status: Rejected" />
  </section>
}

function ReminderRow({ reminder, onOpen }: { reminder: ApplicationReminder; onOpen?: (applicationId: number) => void }) {
  const when = reminder.type === 'interview' && reminder.due_at
    ? formatDateTime(reminder.due_at)
    : reminder.type === 'pending' ? `${STATUS_LABEL[reminder.status]} with no recent update` : `${formatDate(reminder.due_date)} · ${relativeDays(reminder.days_until)}`
  return <li className={`reminder-row ${reminder.overdue ? 'overdue' : ''}`}>
    <span className={`skill-status ${reminder.overdue ? 'missing' : reminder.type === 'interview' ? 'strong' : 'adequate'}`}>{reminder.overdue ? `${REMINDER_LABEL[reminder.type]} · overdue` : REMINDER_LABEL[reminder.type]}</span>
    <div>
      <strong>{reminder.job_title} · {reminder.company}</strong>
      <small>{when}</small>
    </div>
    {onOpen && <button className="text-button" onClick={() => onOpen(reminder.application_id)}>Open -&gt;</button>}
  </li>
}

export function ApplicationReminderList({ reminders, onOpen, emptyText = 'No upcoming application actions.' }: { reminders: ApplicationReminder[]; onOpen?: (applicationId: number) => void; emptyText?: string }) {
  if (reminders.length === 0) return <p className="muted">{emptyText}</p>
  return <ul className="reminder-list">{reminders.map((reminder) => <ReminderRow key={`${reminder.type}-${reminder.application_id}`} reminder={reminder} onOpen={onOpen} />)}</ul>
}

// Dashboard panel: real summary + reminders, or honest loading/error states.
export function ApplicationActivity({ onOpenTracker, onOpenApplication }: { onOpenTracker: () => void; onOpenApplication: (applicationId: number) => void }) {
  const { summary, reminders, state, error, reload } = useApplicationOverview()
  return <section className="card comparison-card application-activity">
    <div className="card-heading"><div><p className="eyebrow">APPLICATION ACTIVITY</p><h3>From your application tracker</h3></div><button className="text-button" onClick={onOpenTracker}>Open tracker -&gt;</button></div>
    {state === 'loading' && <p className="muted" role="status">Loading application activity...</p>}
    {state === 'error' && <div className="error-notice" role="alert">{error} <button className="text-button" onClick={() => void reload()}>Retry</button></div>}
    {state === 'ready' && summary && reminders && <>
      <div className="activity-metrics">
        <div><strong>{summary.total_applications}</strong><small>Total</small></div>
        <div><strong>{summary.active_applications}</strong><small>Active</small></div>
        <div><strong>{summary.upcoming_deadlines}</strong><small>Deadlines (not yet applied, next {summary.upcoming_deadline_window_days} days)</small></div>
        <div><strong>{summary.interviews_scheduled}</strong><small>Interviews scheduled</small></div>
        <div><strong>{summary.offers_received}</strong><small>Offers</small></div>
      </div>
      {summary.total_applications === 0
        ? <p className="muted">No applications tracked yet. Add an opportunity from Career Recommendations or add an external application in the tracker.</p>
        : <ApplicationReminderList reminders={reminders.reminders.slice(0, 5)} onOpen={onOpenApplication} />}
    </>}
  </section>
}

type TrackState = { kind: 'checking' } | { kind: 'untracked' } | { kind: 'saving' } | { kind: 'tracked'; application: Application; justAdded: boolean } | { kind: 'error'; message: string }

// "Add to Tracker" for a canonical opportunity. Only the job_id is sent; the backend
// snapshots company/title/etc. A 409 means it is already tracked, which is shown as
// such (with a link) rather than as a failure.
export function TrackJobButton({ jobId, onOpenApplication }: { jobId: string; onOpenApplication: (applicationId: number) => void }) {
  const [state, setState] = useState<TrackState>({ kind: 'checking' })

  useEffect(() => {
    let cancelled = false
    setState({ kind: 'checking' })
    void findApplicationForJob(jobId)
      .then((existing) => { if (!cancelled) setState(existing ? { kind: 'tracked', application: existing, justAdded: false } : { kind: 'untracked' }) })
      .catch(() => { if (!cancelled) setState({ kind: 'untracked' }) })
    return () => { cancelled = true }
  }, [jobId])

  const track = async () => {
    setState({ kind: 'saving' })
    try {
      setState({ kind: 'tracked', application: await createApplicationFromJob({ job_id: jobId }), justAdded: true })
    } catch (error: unknown) {
      if (error instanceof ApplicationApiError && error.status === 409) {
        const existing = await findApplicationForJob(jobId).catch(() => null)
        if (existing) { setState({ kind: 'tracked', application: existing, justAdded: false }); return }
      }
      setState({ kind: 'error', message: errorMessage(error, 'We could not add this opportunity to your tracker.') })
    }
  }

  if (state.kind === 'checking') return <span className="muted track-state" role="status">Checking tracker...</span>
  if (state.kind === 'tracked') return <span className="track-state" role="status">
    <span className="skill-status strong">{state.justAdded ? 'Added to tracker' : 'Already tracked'} · {STATUS_LABEL[state.application.status]}</span>
    <button className="text-button" onClick={() => onOpenApplication(state.application.id)}>View in tracker -&gt;</button>
  </span>
  return <span className="track-state">
    <button className="primary-button" onClick={() => void track()} disabled={state.kind === 'saving'}>{state.kind === 'saving' ? 'Adding...' : 'Add to Tracker'}</button>
    {state.kind === 'error' && <span className="track-error" role="alert">{state.message}</span>}
  </span>
}

type ArtifactKind = 'customization' | 'interview_preparation'
const ARTIFACT_FIELD = { customization: 'customization_id', interview_preparation: 'interview_preparation_id' } as const
const ARTIFACT_NOUN = { customization: 'these application materials', interview_preparation: 'this interview preparation' } as const

// Shown inside the Customize / Interview Prep workspaces: links the version on screen
// to the tracked application for the same opportunity (the backend re-checks
// ownership and job compatibility).
export function TrackerLinkPanel({ kind, jobId, artifactId, onOpenApplication }: { kind: ArtifactKind; jobId: string; artifactId: number; onOpenApplication: (applicationId: number) => void }) {
  const [application, setApplication] = useState<Application | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'saving' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const field = ARTIFACT_FIELD[kind]

  useEffect(() => {
    let cancelled = false
    setState('loading'); setMessage('')
    void findApplicationForJob(jobId)
      .then((found) => { if (!cancelled) { setApplication(found); setState('ready') } })
      .catch((error: unknown) => { if (!cancelled) { setState('error'); setMessage(errorMessage(error, 'We could not check your application tracker.')) } })
    return () => { cancelled = true }
  }, [jobId])

  const link = async () => {
    setState('saving'); setMessage('')
    const linkPayload = kind === 'customization' ? { customization_id: artifactId } : { interview_preparation_id: artifactId }
    try {
      const saved = application
        ? await updateApplication(application.id, linkPayload)
        : await createApplicationFromJob({ job_id: jobId, ...linkPayload })
      setApplication(saved)
      setState('ready')
    } catch (error: unknown) {
      setState('error')
      setMessage(errorMessage(error, 'We could not link this to your application.'))
    }
  }

  const linked = application !== null && application[field] === artifactId
  return <section className="card tracker-link-panel">
    <p className="eyebrow">APPLICATION TRACKER</p>
    {state === 'loading' && <p className="muted" role="status">Checking your application tracker...</p>}
    {state === 'error' && <div className="error-notice" role="alert">{message}</div>}
    {state !== 'loading' && (application && linked
      ? <p className="muted">This version is linked to your tracked application ({STATUS_LABEL[application.status]}).</p>
      : application
        ? <p className="muted">This opportunity is in your tracker ({STATUS_LABEL[application.status]}). {application[field] !== null ? 'A different version is currently linked.' : `Link ${ARTIFACT_NOUN[kind]} to it?`}</p>
        : <p className="muted">This opportunity is not in your application tracker yet.</p>)}
    <div className="detail-actions">
      {state !== 'loading' && !linked && <button className="secondary-button" disabled={state === 'saving'} onClick={() => void link()}>{state === 'saving' ? 'Linking...' : application ? 'Link this version' : 'Add to Tracker and link'}</button>}
      {application && <button className="text-button" onClick={() => onOpenApplication(application.id)}>Open application -&gt;</button>}
    </div>
  </section>
}
