import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { PageHeading } from '../common'
import {
  APPLICATION_STATUSES, createManualApplication, listApplications,
  type Application, type ApplicationFilters, type ApplicationSort, type ApplicationStatus, type ManualApplicationCreate,
} from '../../services/applicationService'
import {
  EMPLOYMENT_TYPE_SUGGESTIONS, INTERVIEW_STATUS_LABEL, STATUS_LABEL, STATUS_TONE, WORK_MODES,
  errorMessage, formatDate, formatDateTime,
} from './applicationFormat'
import { ApplicationReminderList, ApplicationSummaryStats } from './ApplicationWidgets'
import { useApplicationOverview } from './useApplicationOverview'

type ActiveFilter = 'all' | 'active' | 'completed'
type FilterForm = { q: string; status: ApplicationStatus | ''; active: ActiveFilter; deadline_from: string; deadline_to: string; applied_from: string; applied_to: string; sort: ApplicationSort }

const EMPTY_FILTERS: FilterForm = { q: '', status: '', active: 'all', deadline_from: '', deadline_to: '', applied_from: '', applied_to: '', sort: 'updated_desc' }
const SORT_LABEL: Record<ApplicationSort, string> = {
  updated_desc: 'Recently updated', created_desc: 'Recently added', deadline_asc: 'Deadline (soonest first)',
  applied_desc: 'Application date (newest first)', company_asc: 'Company (A–Z)',
}

const toApiFilters = (form: FilterForm, q: string): ApplicationFilters => ({
  q: q || undefined,
  status: form.status ? [form.status] : undefined,
  active: form.active === 'all' ? undefined : form.active === 'active',
  deadline_from: form.deadline_from || undefined,
  deadline_to: form.deadline_to || undefined,
  applied_from: form.applied_from || undefined,
  applied_to: form.applied_to || undefined,
  sort: form.sort,
})

// Reversed ranges are caught here with plain wording; the backend would reject them too.
const rangeError = (form: FilterForm): string => {
  if (form.deadline_from && form.deadline_to && form.deadline_from > form.deadline_to) return 'The deadline "from" date must be on or before the "to" date.'
  if (form.applied_from && form.applied_to && form.applied_from > form.applied_to) return 'The application-date "from" date must be on or before the "to" date.'
  return ''
}

const hasFilters = (form: FilterForm) => Object.entries(form).some(([key, value]) => key !== 'sort' && value !== EMPTY_FILTERS[key as keyof FilterForm])

function ApplicationCard({ application, onOpen }: { application: Application; onOpen: () => void }) {
  return <article className="card application-card">
    <div className="card-heading">
      <div>
        <h3>{application.job_title}</h3>
        <p className="muted">{application.company}{application.location ? ` · ${application.location}` : ''}</p>
      </div>
      <span className={`skill-status ${STATUS_TONE[application.status]}`}>{STATUS_LABEL[application.status]}</span>
    </div>
    <div className="tag-row">
      {application.employment_type && <span className="opportunity-type-chip">{application.employment_type}</span>}
      <span>{application.source === 'dataset' ? 'From Careers' : 'External'}</span>
      {application.customization_id !== null && <span>Materials linked</span>}
      {application.interview_preparation_id !== null && <span>Interview prep linked</span>}
    </div>
    <dl className="application-facts">
      {application.deadline && <><dt>Deadline</dt><dd>{formatDate(application.deadline)}</dd></>}
      {application.applied_date && <><dt>Applied</dt><dd>{formatDate(application.applied_date)}</dd></>}
      {application.interview_at && <><dt>Interview</dt><dd>{formatDateTime(application.interview_at)}{application.interview_status ? ` · ${INTERVIEW_STATUS_LABEL[application.interview_status]}` : ''}</dd></>}
      {application.follow_up_date && <><dt>Follow up</dt><dd>{formatDate(application.follow_up_date)}</dd></>}
      <dt>Updated</dt><dd>{formatDateTime(application.updated_at)}</dd>
    </dl>
    <button className="text-button" onClick={onOpen}>View / edit →</button>
  </article>
}

const EMPTY_MANUAL: ManualApplicationCreate = { company: '', job_title: '' }

function ManualApplicationForm({ onCreated, onCancel }: { onCreated: (application: Application) => void; onCancel: () => void }) {
  const [form, setForm] = useState<ManualApplicationCreate>(EMPTY_MANUAL)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const set = (field: keyof ManualApplicationCreate) => (event: { target: { value: string } }) => setForm({ ...form, [field]: event.target.value })

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!form.company.trim() || !form.job_title.trim()) { setError('Company and role title are required.'); return }
    // Empty optional inputs are omitted entirely rather than sent as blank values.
    const payload = Object.fromEntries(Object.entries(form).filter(([, value]) => typeof value === 'string' ? value.trim() !== '' : value !== undefined)) as ManualApplicationCreate
    setSaving(true); setError('')
    try {
      onCreated(await createManualApplication(payload))
      setForm(EMPTY_MANUAL)
    } catch (reason: unknown) {
      setError(errorMessage(reason, 'We could not add this application.'))
    } finally {
      setSaving(false)
    }
  }

  return <form className="card form-card tracker-form" onSubmit={(event) => void submit(event)}>
    <div className="card-heading"><div><p className="eyebrow">ADD APPLICATION</p><h3>An opportunity from outside Careers</h3></div></div>
    {error && <div className="error-notice" role="alert">{error}</div>}
    <div className="form-grid">
      <label>Company *<input value={form.company} onChange={set('company')} maxLength={255} required disabled={saving} /></label>
      <label>Role / job title *<input value={form.job_title} onChange={set('job_title')} maxLength={255} required disabled={saving} /></label>
      <label>Employment type<input value={form.employment_type ?? ''} onChange={set('employment_type')} list="employment-type-options" maxLength={64} disabled={saving} /></label>
      <datalist id="employment-type-options">{EMPLOYMENT_TYPE_SUGGESTIONS.map((type) => <option key={type} value={type} />)}</datalist>
      <label>Work mode<select value={form.work_mode ?? ''} onChange={set('work_mode')} disabled={saving}><option value="">Not specified</option>{WORK_MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}</select></label>
      <label>Location<input value={form.location ?? ''} onChange={set('location')} maxLength={255} disabled={saving} /></label>
      <label>Status<select value={form.status ?? 'saved'} onChange={set('status')} disabled={saving}>{APPLICATION_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABEL[status]}</option>)}</select></label>
      <label>Application date<input type="date" value={form.applied_date ?? ''} onChange={set('applied_date')} disabled={saving} /></label>
      <label>Deadline<input type="date" value={form.deadline ?? ''} onChange={set('deadline')} disabled={saving} /></label>
      <label>Follow-up date<input type="date" value={form.follow_up_date ?? ''} onChange={set('follow_up_date')} disabled={saving} /></label>
      <label className="full-width">Job description<textarea value={form.job_description ?? ''} onChange={set('job_description')} maxLength={20000} disabled={saving} /></label>
      <label className="full-width">Notes<textarea value={form.notes ?? ''} onChange={set('notes')} maxLength={10000} disabled={saving} /></label>
    </div>
    <div className="detail-actions">
      <button className="primary-button" disabled={saving}>{saving ? 'Adding...' : 'Add application'}</button>
      <button type="button" className="text-button" onClick={onCancel} disabled={saving}>Cancel</button>
    </div>
  </form>
}

export function ApplicationTrackerView({ onOpenApplication, onBrowseOpportunities }: { onOpenApplication: (applicationId: number) => void; onBrowseOpportunities: () => void }) {
  const overview = useApplicationOverview()
  const [filters, setFilters] = useState<FilterForm>(EMPTY_FILTERS)
  const [debouncedQ, setDebouncedQ] = useState('')
  const [applications, setApplications] = useState<Application[] | null>(null)
  const [listState, setListState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [listError, setListError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [notice, setNotice] = useState<Application | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => { const timer = window.setTimeout(() => setDebouncedQ(filters.q.trim()), 300); return () => window.clearTimeout(timer) }, [filters.q])

  useEffect(() => {
    let cancelled = false
    if (rangeError(filters)) return
    setListState('loading'); setListError('')
    void listApplications(toApiFilters(filters, debouncedQ))
      .then((result) => { if (!cancelled) { setApplications(result); setListState('ready') } })
      .catch((reason: unknown) => { if (!cancelled) { setListState('error'); setListError(errorMessage(reason, 'We could not load your applications.')) } })
    return () => { cancelled = true }
    // `filters.q` is applied through `debouncedQ` only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQ, filters.status, filters.active, filters.deadline_from, filters.deadline_to, filters.applied_from, filters.applied_to, filters.sort, refreshKey])

  const set = <K extends keyof FilterForm>(key: K, value: FilterForm[K]) => setFilters((current) => ({ ...current, [key]: value }))
  const handleCreated = (application: Application) => {
    setShowForm(false); setNotice(application)
    setRefreshKey((key) => key + 1)
    void overview.reload()
  }
  const filtered = hasFilters(filters)
  const invalidRange = rangeError(filters)

  return <>
    <PageHeading eyebrow="APPLICATION TRACKER" title="Every application, one place." lede="Track opportunities from Careers and external applications — statuses, deadlines, interviews and follow-ups."
      action={<button className="primary-button" onClick={() => { setShowForm((open) => !open); setNotice(null) }}>{showForm ? 'Close form' : 'Add application'}</button>} />

    {overview.state === 'loading' && <p className="muted" role="status">Loading your application summary...</p>}
    {overview.state === 'error' && <div className="error-notice" role="alert">{overview.error} <button className="text-button" onClick={() => void overview.reload()}>Retry</button></div>}
    {overview.state === 'ready' && overview.summary && <ApplicationSummaryStats summary={overview.summary} />}

    {notice && <div className="success-notice" role="status">Added {notice.job_title} at {notice.company}. <button className="text-button" onClick={() => onOpenApplication(notice.id)}>Open it →</button></div>}
    {showForm && <ManualApplicationForm onCreated={handleCreated} onCancel={() => setShowForm(false)} />}

    <div className="tracker-layout">
      <section className="tracker-main">
        <form className="card tracker-filters" onSubmit={(event) => event.preventDefault()} aria-label="Filter applications">
          <label className="filter-search">Search company or role<input type="search" value={filters.q} onChange={(event) => set('q', event.target.value)} placeholder="e.g. Acme or data analyst" /></label>
          <div className="tag-row" role="group" aria-label="Show applications">
            {(['all', 'active', 'completed'] as ActiveFilter[]).map((option) => <button type="button" key={option} className={`text-button ${filters.active === option ? 'active' : ''}`} aria-pressed={filters.active === option} onClick={() => set('active', option)}>{option === 'all' ? 'All' : option === 'active' ? 'Active' : 'Completed'}</button>)}
          </div>
          <div className="filter-grid">
            <label>Status<select value={filters.status} onChange={(event) => set('status', event.target.value as ApplicationStatus | '')}><option value="">All statuses</option>{APPLICATION_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABEL[status]}</option>)}</select></label>
            <label>Sort by<select value={filters.sort} onChange={(event) => set('sort', event.target.value as ApplicationSort)}>{(Object.keys(SORT_LABEL) as ApplicationSort[]).map((sort) => <option key={sort} value={sort}>{SORT_LABEL[sort]}</option>)}</select></label>
            <label>Deadline from<input type="date" value={filters.deadline_from} onChange={(event) => set('deadline_from', event.target.value)} /></label>
            <label>Deadline to<input type="date" value={filters.deadline_to} onChange={(event) => set('deadline_to', event.target.value)} /></label>
            <label>Applied from<input type="date" value={filters.applied_from} onChange={(event) => set('applied_from', event.target.value)} /></label>
            <label>Applied to<input type="date" value={filters.applied_to} onChange={(event) => set('applied_to', event.target.value)} /></label>
          </div>
          {invalidRange && <p className="track-error" role="alert">{invalidRange}</p>}
          {filtered && <button type="button" className="text-button" onClick={() => setFilters({ ...EMPTY_FILTERS, sort: filters.sort })}>Clear filters</button>}
        </form>

        {!invalidRange && <>
        {listState === 'loading' && applications === null && <p className="muted" role="status">Loading applications...</p>}
        {listState === 'error' && <div className="error-notice" role="alert">{listError} <button className="text-button" onClick={() => setRefreshKey((key) => key + 1)}>Retry</button></div>}
        {listState !== 'error' && applications !== null && applications.length === 0 && (filtered
          ? <div className="architecture-note" role="status">No applications match these filters.</div>
          : <div className="architecture-note tracker-empty" role="status">
            <div><strong>No applications tracked yet.</strong><p>Add an opportunity from Career Recommendations with “Add to Tracker”, or add an external application manually.</p></div>
            <div className="detail-actions"><button className="secondary-button" onClick={onBrowseOpportunities}>Browse opportunities</button><button className="secondary-button" onClick={() => setShowForm(true)}>Add application manually</button></div>
          </div>)}
        {listState !== 'error' && applications !== null && applications.length > 0 && <section className="application-list" aria-busy={listState === 'loading'}>
          {applications.map((application) => <ApplicationCard key={application.id} application={application} onOpen={() => onOpenApplication(application.id)} />)}
        </section>}
        </>}
      </section>

      <aside className="card tracker-reminders">
        <p className="eyebrow">UPCOMING ACTIONS</p>
        <h3>Next {overview.reminders?.window_days ?? 7} days</h3>
        {overview.state === 'loading' && <p className="muted" role="status">Loading reminders...</p>}
        {overview.state === 'error' && <p className="muted">Reminders are unavailable right now.</p>}
        {overview.state === 'ready' && overview.reminders && <ApplicationReminderList reminders={overview.reminders.reminders} onOpen={onOpenApplication} />}
      </aside>
    </div>
  </>
}
