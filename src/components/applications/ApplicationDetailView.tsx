import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { PageHeading } from '../common'
import {
  APPLICATION_STATUSES, deleteApplication, getApplication, getApplicationReminders, updateApplication,
  type Application, type ApplicationReminder, type ApplicationStatus, type ApplicationUpdate, type InterviewStatus,
} from '../../services/applicationService'
import { listCustomizations, type ApplicationCustomizationSummary } from '../../services/customizationService'
import { listInterviewPreparations, type InterviewPreparationSummary } from '../../services/interviewPrepService'
import {
  EMPLOYMENT_TYPE_SUGGESTIONS, INTERVIEW_STATUS_LABEL, STATUS_LABEL, STATUS_TONE, WORK_MODES,
  browserTimeZone, errorMessage, formatDateTime, fromDatetimeLocal, toDatetimeLocal,
} from './applicationFormat'
import { ApplicationReminderList } from './ApplicationWidgets'

type Draft = {
  company: string; job_title: string; employment_type: string; location: string; work_mode: string; job_description: string
  applied_date: string; deadline: string; follow_up_date: string; interview_at: string; interview_status: InterviewStatus | ''; notes: string
}

const draftFrom = (application: Application): Draft => ({
  company: application.company, job_title: application.job_title,
  employment_type: application.employment_type ?? '', location: application.location ?? '', work_mode: application.work_mode ?? '',
  job_description: application.job_description ?? '', applied_date: application.applied_date ?? '', deadline: application.deadline ?? '',
  follow_up_date: application.follow_up_date ?? '', interview_at: toDatetimeLocal(application.interview_at),
  interview_status: application.interview_status ?? '', notes: application.notes ?? '',
})

// Builds a PATCH with only the fields that actually changed; empty inputs clear the
// field (null). Opportunity details are only sent for manual applications — the
// backend rejects edits to a dataset application's snapshot.
const changedFields = (application: Application, draft: Draft): ApplicationUpdate | string => {
  const original = draftFrom(application)
  const update: Record<string, string | null> = {}
  const editable: (keyof Draft)[] = ['applied_date', 'deadline', 'follow_up_date', 'interview_status', 'notes']
  if (application.source === 'manual') editable.push('company', 'job_title', 'employment_type', 'location', 'work_mode', 'job_description')
  for (const key of editable) {
    if (draft[key] !== original[key]) update[key] = draft[key].trim() === '' ? null : draft[key]
  }
  if (update.company === null || update.job_title === null) return 'Company and role title are required.'
  if (draft.interview_at !== original.interview_at) {
    const instant = fromDatetimeLocal(draft.interview_at)
    if (draft.interview_at && instant === null) return 'Please enter a valid interview date and time.'
    update.interview_at = instant
  }
  return update as ApplicationUpdate
}

function LinkedMaterials<T extends { id: number; version: number; created_at: string; stale: boolean }>({ title, linkedId, versions, loadError, onLink, onUnlink, onOpen, openLabel, saving }: {
  title: string; linkedId: number | null; versions: T[] | null; loadError: string
  onLink: (id: number) => void; onUnlink: () => void; onOpen: () => void; openLabel: string; saving: boolean
}) {
  const [choice, setChoice] = useState<number | ''>('')
  const linkedVersion = versions?.find((version) => version.id === linkedId) ?? null
  const candidates = versions?.filter((version) => version.id !== linkedId) ?? []
  return <div className="linked-material">
    <strong>{title}</strong>
    {linkedId !== null
      ? <p className="muted">{linkedVersion ? `Linked: version ${linkedVersion.version}, generated ${formatDateTime(linkedVersion.created_at)}${linkedVersion.stale ? ' (your resume has changed since)' : ''}.` : `Linked record #${linkedId} (generated from a different resume than your current one).`}</p>
      : <p className="muted">Nothing linked yet.</p>}
    {loadError && <p className="muted">{loadError}</p>}
    {versions !== null && versions.length === 0 && linkedId === null && <p className="muted">No generated versions for this opportunity yet.</p>}
    <div className="detail-actions">
      {candidates.length > 0 && <>
        <label className="inline-select">Version<select value={choice} onChange={(event) => setChoice(event.target.value ? Number(event.target.value) : '')} disabled={saving}><option value="">Choose a version</option>{candidates.map((version) => <option key={version.id} value={version.id}>Version {version.version} · {formatDateTime(version.created_at)}</option>)}</select></label>
        <button className="secondary-button" disabled={saving || choice === ''} onClick={() => { if (choice !== '') onLink(choice) }}>Link</button>
      </>}
      {linkedId !== null && <button className="text-button" disabled={saving} onClick={onUnlink}>Unlink</button>}
      <button className="text-button" onClick={onOpen}>{openLabel} →</button>
    </div>
  </div>
}

export function ApplicationDetailView({ applicationId, resumeId, onBack, onOpenCustomization, onOpenInterviewPrep, onOpenJob }: {
  applicationId: number | null
  resumeId: number | null
  onBack: () => void
  onOpenCustomization: (jobId: string) => void
  onOpenInterviewPrep: (jobId: string) => void
  onOpenJob: (jobId: string) => void
}) {
  const [application, setApplication] = useState<Application | null>(null)
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'missing' | 'error'>('loading')
  const [loadError, setLoadError] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [statusChoice, setStatusChoice] = useState<ApplicationStatus>('saved')
  const [saving, setSaving] = useState<'' | 'status' | 'details' | 'link' | 'delete'>('')
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [reminders, setReminders] = useState<ApplicationReminder[] | null>(null)
  const [customizations, setCustomizations] = useState<ApplicationCustomizationSummary[] | null>(null)
  const [preparations, setPreparations] = useState<InterviewPreparationSummary[] | null>(null)
  const [artifactError, setArtifactError] = useState('')

  const apply = (next: Application) => { setApplication(next); setDraft(draftFrom(next)); setStatusChoice(next.status) }

  const loadReminders = useCallback(async (id: number) => {
    try {
      const result = await getApplicationReminders(60)
      setReminders(result.reminders.filter((reminder) => reminder.application_id === id))
    } catch {
      setReminders(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoadState('loading'); setLoadError(''); setMessage(null); setConfirmDelete(false); setApplication(null)
    if (applicationId === null) { setLoadState('missing'); return }
    void getApplication(applicationId).then((result) => {
      if (cancelled) return
      if (result === null) { setLoadState('missing'); return }
      apply(result); setLoadState('ready')
      void loadReminders(result.id)
    }).catch((reason: unknown) => { if (!cancelled) { setLoadState('error'); setLoadError(errorMessage(reason, 'We could not load this application.')) } })
    return () => { cancelled = true }
  }, [applicationId, loadReminders])

  const jobId = application?.job_id ?? null
  useEffect(() => {
    let cancelled = false
    setCustomizations(null); setPreparations(null); setArtifactError('')
    if (jobId === null || resumeId === null) return
    void Promise.all([listCustomizations(resumeId, jobId), listInterviewPreparations(resumeId, jobId)])
      .then(([customizationList, preparationList]) => { if (!cancelled) { setCustomizations(customizationList); setPreparations(preparationList) } })
      .catch((reason: unknown) => { if (!cancelled) setArtifactError(errorMessage(reason, 'We could not load generated materials.')) })
    return () => { cancelled = true }
  }, [jobId, resumeId])

  const save = async (kind: 'status' | 'details' | 'link', update: ApplicationUpdate, successText: string) => {
    if (!application) return
    setSaving(kind); setMessage(null)
    try {
      const saved = await updateApplication(application.id, update)
      apply(saved)
      setMessage({ kind: 'success', text: successText })
      void loadReminders(saved.id)
    } catch (reason: unknown) {
      setMessage({ kind: 'error', text: errorMessage(reason, 'We could not save your changes.') })
    } finally {
      setSaving('')
    }
  }

  const saveDetails = (event: FormEvent) => {
    event.preventDefault()
    if (!application || !draft) return
    const update = changedFields(application, draft)
    if (typeof update === 'string') { setMessage({ kind: 'error', text: update }); return }
    if (Object.keys(update).length === 0) { setMessage({ kind: 'success', text: 'No changes to save.' }); return }
    void save('details', update, 'Application details saved.')
  }

  const remove = async () => {
    if (!application) return
    setSaving('delete'); setMessage(null)
    try {
      await deleteApplication(application.id)
      onBack()
    } catch (reason: unknown) {
      setSaving('')
      setMessage({ kind: 'error', text: errorMessage(reason, 'We could not delete this application.') })
    }
  }

  const back = <button className="text-button" onClick={onBack}>Back to tracker →</button>
  if (loadState === 'loading') return <PageHeading eyebrow="APPLICATION" title="Loading application..." lede="" action={back} />
  if (loadState === 'missing') return <><PageHeading eyebrow="APPLICATION" title="Application not found." lede="It may have been deleted, or it is not part of your tracker." action={back} /></>
  if (loadState === 'error' || !application || !draft) return <><PageHeading eyebrow="APPLICATION" title="We could not load this application." lede={loadError} action={back} /><button className="secondary-button" onClick={() => window.location.reload()}>Retry</button></>

  const isDataset = application.source === 'dataset'
  const busy = saving !== ''
  const field = (key: keyof Draft) => (event: { target: { value: string } }) => setDraft({ ...draft, [key]: event.target.value })

  return <>
    <PageHeading eyebrow={isDataset ? `APPLICATION · ${application.job_id}` : 'APPLICATION · EXTERNAL'} title={application.job_title}
      lede={<>{application.employment_type && <span className="opportunity-type-chip inline">{application.employment_type}</span>}{application.company}{application.location ? ` · ${application.location}` : ''}{application.work_mode ? ` · ${application.work_mode}` : ''}</>}
      action={back} />

    {message && <div className={message.kind === 'success' ? 'success-notice' : 'error-notice'} role={message.kind === 'success' ? 'status' : 'alert'}>{message.text}</div>}

    <section className="card comparison-card">
      <div className="card-heading">
        <div><p className="eyebrow">STATUS</p><h3><span className={`skill-status ${STATUS_TONE[application.status]}`}>{STATUS_LABEL[application.status]}</span></h3></div>
        <small className="muted">{application.is_active ? 'Active' : 'Completed'} · status since {formatDateTime(application.status_updated_at)}</small>
      </div>
      <div className="detail-actions">
        <label className="inline-select">Change status<select value={statusChoice} onChange={(event) => setStatusChoice(event.target.value as ApplicationStatus)} disabled={busy}>{APPLICATION_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABEL[status]}</option>)}</select></label>
        <button className="primary-button" disabled={busy || statusChoice === application.status} onClick={() => void save('status', { status: statusChoice }, `Status updated to ${STATUS_LABEL[statusChoice]}.`)}>{saving === 'status' ? 'Updating...' : 'Update status'}</button>
      </div>
      {application.status === 'interview_scheduled' && !application.interview_at && <div className="architecture-note" role="status">This application is marked Interview Scheduled, but no interview date is set yet. Add the date and time below so it appears in your reminders and interview count.</div>}
    </section>

    {reminders !== null && reminders.length > 0 && <section className="card comparison-card"><p className="eyebrow">UPCOMING FOR THIS APPLICATION</p><ApplicationReminderList reminders={reminders} /></section>}

    <form className="card form-card tracker-form" onSubmit={saveDetails}>
      <div className="card-heading"><div><p className="eyebrow">DETAILS</p><h3>Dates, interview and notes</h3></div></div>
      <div className="form-grid">
        {isDataset ? <p className="muted full-width">Opportunity details come from the Careers listing and stay as they were when you tracked it. <button type="button" className="text-button" onClick={() => onOpenJob(application.job_id as string)}>View opportunity →</button></p> : <>
          <label>Company *<input value={draft.company} onChange={field('company')} maxLength={255} required disabled={busy} /></label>
          <label>Role / job title *<input value={draft.job_title} onChange={field('job_title')} maxLength={255} required disabled={busy} /></label>
          <label>Employment type<input value={draft.employment_type} onChange={field('employment_type')} list="detail-employment-types" maxLength={64} disabled={busy} /></label>
          <datalist id="detail-employment-types">{EMPLOYMENT_TYPE_SUGGESTIONS.map((type) => <option key={type} value={type} />)}</datalist>
          <label>Work mode<select value={draft.work_mode} onChange={field('work_mode')} disabled={busy}><option value="">Not specified</option>{[...new Set([...WORK_MODES, ...(draft.work_mode ? [draft.work_mode] : [])])].map((mode) => <option key={mode} value={mode}>{mode}</option>)}</select></label>
          <label className="full-width">Location<input value={draft.location} onChange={field('location')} maxLength={255} disabled={busy} /></label>
        </>}
        <label>Application date<input type="date" value={draft.applied_date} onChange={field('applied_date')} disabled={busy} /></label>
        <label>Deadline<input type="date" value={draft.deadline} onChange={field('deadline')} disabled={busy} /></label>
        <label>Follow-up date<input type="date" value={draft.follow_up_date} onChange={field('follow_up_date')} disabled={busy} /></label>
        <label>Interview status<select value={draft.interview_status} onChange={field('interview_status')} disabled={busy}><option value="">Not set</option>{(Object.keys(INTERVIEW_STATUS_LABEL) as InterviewStatus[]).map((status) => <option key={status} value={status}>{INTERVIEW_STATUS_LABEL[status]}</option>)}</select></label>
        <label className="full-width">Interview date &amp; time <span className="field-hint">(your local time, {browserTimeZone()})</span><input type="datetime-local" value={draft.interview_at} onChange={field('interview_at')} disabled={busy} /></label>
        {!isDataset && <label className="full-width">Job description<textarea value={draft.job_description} onChange={field('job_description')} maxLength={20000} disabled={busy} /></label>}
        <label className="full-width">Notes<textarea value={draft.notes} onChange={field('notes')} maxLength={10000} disabled={busy} /></label>
      </div>
      <div className="detail-actions">
        <button className="primary-button" disabled={busy}>{saving === 'details' ? 'Saving...' : 'Save details'}</button>
        <button type="button" className="text-button" disabled={busy} onClick={() => { setDraft(draftFrom(application)); setMessage(null) }}>Discard changes</button>
      </div>
    </form>

    <section className="card comparison-card">
      <div className="card-heading"><div><p className="eyebrow">GENERATED MATERIALS</p><h3>Resume, cover letter and interview preparation</h3></div></div>
      {!isDataset
        ? <p className="muted">Generated resumes, cover letters and interview preparation are created for opportunities from Career Recommendations, so they can't be linked to an external application.</p>
        : resumeId === null
          ? <p className="muted">Process a resume to view or generate application materials for this opportunity.{application.customization_id !== null || application.interview_preparation_id !== null ? ' Previously linked materials remain attached.' : ''}</p>
          : <div className="linked-materials">
            <LinkedMaterials title="Tailored resume & cover letter" linkedId={application.customization_id} versions={customizations} loadError={artifactError} saving={saving === 'link'}
              onLink={(id) => void save('link', { customization_id: id }, 'Application materials linked.')}
              onUnlink={() => void save('link', { customization_id: null }, 'Application materials unlinked.')}
              onOpen={() => onOpenCustomization(application.job_id as string)} openLabel={customizations && customizations.length > 0 ? 'Open Customize Application' : 'Generate in Customize Application'} />
            <LinkedMaterials title="Interview preparation" linkedId={application.interview_preparation_id} versions={preparations} loadError={artifactError} saving={saving === 'link'}
              onLink={(id) => void save('link', { interview_preparation_id: id }, 'Interview preparation linked.')}
              onUnlink={() => void save('link', { interview_preparation_id: null }, 'Interview preparation unlinked.')}
              onOpen={() => onOpenInterviewPrep(application.job_id as string)} openLabel={preparations && preparations.length > 0 ? 'Open Interview Preparation' : 'Generate in Interview Preparation'} />
          </div>}
    </section>

    <section className="card comparison-card danger-zone">
      <p className="eyebrow">DELETE</p>
      <p className="muted">Removes this application from your tracker. Generated resumes, cover letters and interview preparation are kept.</p>
      {confirmDelete
        ? <div className="detail-actions" role="group" aria-label="Confirm deletion">
          <span>Delete “{application.job_title}” at {application.company}?</span>
          <button className="primary-button danger-button" disabled={busy} onClick={() => void remove()}>{saving === 'delete' ? 'Deleting...' : 'Yes, delete application'}</button>
          <button className="text-button" disabled={busy} onClick={() => setConfirmDelete(false)}>Cancel</button>
        </div>
        : <button className="secondary-button" disabled={busy} onClick={() => setConfirmDelete(true)}>Delete application</button>}
    </section>
  </>
}
