import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, FormEvent } from 'react'
import './App.css'
import './profile.css'
import { getCurrentSession, login, logout, registerAccount, type AuthSession, type AuthUser } from './services/authService'
import { updateProfile, type CandidateProfile, type CandidateProfilePayload } from './services/profileService'
import { createCandidateContext, detectResumeSections, extractResumeText, getJobMatches, getResumeExtraction, getStructuredResume, listProfileResumes, structureResume, uploadResume, type JobMatchResult, type ResumeRecord, type StructuredResume } from './services/resumeService'
import { getJobDetails, searchJobs, type JobPosting, type JobSearchResult } from './services/jobService'
import { analyzeSkillGap, type GapItem, type SkillGapAnalysis } from './services/skillGapService'
import {
  downloadExport, generateCustomization, getCustomization, listCustomizations, regenerateCustomization, updateCustomization,
  type ApplicationCustomization, type ApplicationCustomizationSummary, type EvidenceRecord, type ExportDocument, type ExportFormat,
  type GenerationMode, type KeywordStatus, type TailoredResume,
} from './services/customizationService'
import {
  generateInterviewPreparation, getInterviewPreparation, listInterviewPreparations, regenerateInterviewPreparation, submitMockAnswer,
  type Difficulty, type InterviewPreparation, type InterviewPreparationSummary, type InterviewQuestion,
  type MockAnswerEvaluation, type QuestionCategory, type RevisionPriority,
} from './services/interviewPrepService'

type ResumeLifecycle = 'no_resume' | 'uploading' | 'processing' | 'processed' | 'failed'

type View = 'dashboard' | 'profile' | 'resume' | 'resume-results' | 'careers' | 'job-details' | 'skills' | 'customize' | 'interview-prep' | 'roadmap' | 'assistant' | 'progress' | 'settings'
const nav = [{ id: 'dashboard' as View, label: 'Dashboard', note: 'Your next best action' }, { id: 'profile' as View, label: 'Career Profile', note: 'Your structured context' }, { id: 'resume' as View, label: 'Resume Analyzer', note: 'Upload and feedback' }, { id: 'careers' as View, label: 'Career Recommendations', note: 'Paths that fit you' }, { id: 'skills' as View, label: 'Skill Gap Analysis', note: 'Compare your skills' }, { id: 'roadmap' as View, label: 'Learning Roadmap', note: 'Your learning path' }, { id: 'assistant' as View, label: 'AI Career Assistant', note: 'Contextual guidance' }, { id: 'progress' as View, label: 'Progress Tracker', note: 'Your development' }]
const viewFromPath = (): View => { const path = window.location.pathname; if (path.startsWith('/jobs/')) return 'job-details'; if (path === '/resume/results') return 'resume-results'; if (path === '/customize') return 'customize'; if (path === '/interview-prep') return 'interview-prep'; const match = nav.find((item) => `/${item.id}` === path); return match?.id ?? (path === '/settings' ? 'settings' : 'dashboard') }
const greetingForTime = () => { const hour = new Date().getHours(); return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening' }

type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated'

const initials = (fullName: string) => fullName.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? '').join('') || '?'

function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>('checking')
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [activeProfile, setActiveProfile] = useState<CandidateProfile | null>(null)
  const [view, setView] = useState<View>(viewFromPath)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(() => window.location.pathname.startsWith('/jobs/') ? window.location.pathname.slice('/jobs/'.length) : null)
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [resumeLifecycle, setResumeLifecycle] = useState<ResumeLifecycle>('no_resume')
  const [resumeRestoring, setResumeRestoring] = useState(true)
  const [resumeRecord, setResumeRecord] = useState<ResumeRecord | null>(null)
  const [structuredResume, setStructuredResume] = useState<StructuredResume | null>(null)
  const [notice, setNotice] = useState('')
  const restoreAttempted = useRef(false)

  useEffect(() => {
    let cancelled = false
    getCurrentSession().then((session) => {
      if (cancelled) return
      if (session) {
        setCurrentUser(session.user)
        setActiveProfile(session.profile)
        setAuthStatus('authenticated')
      } else {
        setAuthStatus('unauthenticated')
      }
    }).catch(() => { if (!cancelled) setAuthStatus('unauthenticated') })
    return () => { cancelled = true }
  }, [])
  useEffect(() => { const onPopState = () => setView(viewFromPath()); window.addEventListener('popstate', onPopState); return () => window.removeEventListener('popstate', onPopState) }, [])
  // Restores the active resume purely from the backend (most recently uploaded resume for this profile).
  // Browser storage plays no role here, so ownership can never be spoofed by editing localStorage.
  useEffect(() => {
    if (authStatus !== 'authenticated') return
    if (restoreAttempted.current) return
    restoreAttempted.current = true
    if (activeProfile === null) { setResumeLifecycle('no_resume'); setResumeRestoring(false); return }
    void listProfileResumes(activeProfile.id).then(async (resumes) => {
      const latest = resumes[0] ?? null
      if (!latest) { setResumeLifecycle('no_resume'); return }
      setResumeRecord(latest)
      const structured = await getStructuredResume(latest.id)
      if (structured) {
        setStructuredResume(structured)
        setResumeLifecycle('processed')
        return
      }
      if (latest.status === 'extraction_failed') {
        const extraction = await getResumeExtraction(latest.id).catch(() => null)
        setNotice(extraction?.error_message || 'Resume text extraction failed. Please upload a different file.')
      } else {
        setNotice('Processing did not finish for your last uploaded resume. Please upload it again.')
      }
      setResumeLifecycle('failed')
    }).catch((error: unknown) => {
      setResumeLifecycle('failed')
      setNotice(error instanceof Error ? error.message : 'We could not restore your saved resume.')
    }).finally(() => setResumeRestoring(false))
  }, [authStatus, activeProfile])
  const go = (next: View) => { setView(next); setNotice(''); window.history.pushState({}, '', `/${next === 'dashboard' ? 'dashboard' : next === 'job-details' ? `jobs/${selectedJobId ?? ''}` : next === 'resume-results' ? 'resume/results' : next}`) }
  // Sets the URL directly with the just-selected job id rather than going through
  // go('job-details'), which would otherwise read selectedJobId from this render's
  // closure before the setSelectedJobId update above has been applied.
  const openJobDetails = (jobId: string) => { setSelectedJobId(jobId); setView('job-details'); setNotice(''); window.history.pushState({}, '', `/jobs/${jobId}`) }
  const chooseFile = (file: File | undefined) => { if (!file) return; const extension = file.name.toLowerCase().split('.').pop(); if (!['pdf', 'docx'].includes(extension ?? '')) { setNotice('Please choose a PDF or DOCX resume.'); return }; setResumeFile(file); setResumeLifecycle('no_resume'); setResumeRecord(null); setStructuredResume(null); setNotice('') }
  const analyze = async () => {
    if (!resumeFile) return
    if (activeProfile === null) { setNotice('Your career profile is not ready yet. Please refresh and try again.'); return }
    setResumeLifecycle('uploading'); setNotice('')
    try {
      const uploaded = await uploadResume(activeProfile.id, resumeFile)
      setResumeRecord(uploaded)
      setResumeLifecycle('processing')
      await extractResumeText(uploaded.id)
      await detectResumeSections(uploaded.id)
      const structured = await structureResume(uploaded.id)
      setStructuredResume(structured)
      await createCandidateContext(activeProfile.id, uploaded.id)
      setResumeLifecycle('processed')
      go('resume-results')
    } catch (error: unknown) {
      setResumeLifecycle('failed')
      setNotice(error instanceof Error ? error.message : 'We could not process this resume.')
    }
  }
  // Re-runs extraction/section-detection/structuring against the already-stored
  // resume file for an existing resume record — no new upload. Every step here is
  // an upsert in the backend (extraction, sections, structured data, and candidate
  // context all replace their existing row for this resume id rather than creating
  // a new one), so this always reflects the current parser and never leaves
  // duplicate or conflicting active state.
  const reprocessResume = async () => {
    if (!resumeRecord) return
    setResumeLifecycle('processing'); setNotice('')
    try {
      await extractResumeText(resumeRecord.id)
      await detectResumeSections(resumeRecord.id)
      const structured = await structureResume(resumeRecord.id)
      setStructuredResume(structured)
      if (activeProfile) await createCandidateContext(activeProfile.id, resumeRecord.id)
      setResumeLifecycle('processed')
    } catch (error: unknown) {
      setResumeLifecycle('failed')
      setNotice(error instanceof Error ? error.message : 'We could not reprocess this resume.')
    }
  }
  const handleAuthenticated = (session: AuthSession) => { setCurrentUser(session.user); setActiveProfile(session.profile); setAuthStatus('authenticated') }
  const handleLogout = async () => {
    try { await logout() } finally {
      setCurrentUser(null)
      setActiveProfile(null)
      setStructuredResume(null)
      setResumeFile(null)
      setResumeRecord(null)
      setResumeLifecycle('no_resume')
      setResumeRestoring(true)
      restoreAttempted.current = false
      setAuthStatus('unauthenticated')
      window.history.pushState({}, '', '/')
    }
  }
  const activeResumeId = resumeLifecycle === 'processed' ? resumeRecord?.id ?? null : null
  const content = view === 'profile' ? <ProfileView profile={activeProfile} onProfileSaved={setActiveProfile} /> : view === 'resume' ? <RealResumeView file={resumeFile} lifecycle={resumeLifecycle} restoring={resumeRestoring} notice={notice} resumeRecord={resumeRecord} onDrop={(event) => { event.preventDefault(); chooseFile(event.dataTransfer.files[0]) }} onFileChange={(event) => chooseFile(event.target.files?.[0])} onAnalyze={analyze} onReprocess={reprocessResume} /> : view === 'resume-results' ? <RealResumeResults structuredResume={structuredResume} onNavigate={go} /> : view === 'careers' ? <CareersView resumeId={activeResumeId} onOpenJob={openJobDetails} /> : view === 'job-details' ? <JobDetailsView jobId={selectedJobId} resumeId={activeResumeId} onBack={() => go('careers')} onAnalyzeSkillGap={() => go('skills')} onCustomizeApplication={() => go('customize')} onInterviewPrep={() => go('interview-prep')} /> : view === 'skills' ? <SkillsView resumeId={activeResumeId} jobId={selectedJobId} onRoadmap={() => go('roadmap')} onSearchJobs={() => go('careers')} onCustomizeApplication={() => go('customize')} onInterviewPrep={() => go('interview-prep')} /> : view === 'customize' ? <CustomizeView resumeId={activeResumeId} jobId={selectedJobId} structuredResume={structuredResume} onSearchJobs={() => go('careers')} onInterviewPrep={() => go('interview-prep')} /> : view === 'interview-prep' ? <InterviewPrepView resumeId={activeResumeId} jobId={selectedJobId} structuredResume={structuredResume} onSearchJobs={() => go('careers')} /> : view === 'roadmap' ? <RoadmapView resumeId={activeResumeId} /> : view === 'assistant' ? <AssistantView profile={activeProfile} resumeLifecycle={resumeLifecycle} structuredResume={structuredResume} onNavigate={go} /> : view === 'progress' ? <ProgressView profile={activeProfile} resumeLifecycle={resumeLifecycle} structuredResume={structuredResume} /> : view === 'settings' ? <SettingsView /> : <DashboardView currentUser={currentUser} profile={activeProfile} resumeLifecycle={resumeLifecycle} resumeRestoring={resumeRestoring} resumeRecord={resumeRecord} structuredResume={structuredResume} notice={notice} onNavigate={go} />
  if (authStatus === 'checking') return <main className="auth-page"><section className="auth-panel"><div className="auth-brand"><span>AC</span><div><strong>AI Career</strong><small>Companion</small></div></div><p className="muted">Loading your workspace...</p></section></main>
  if (authStatus === 'unauthenticated') { const path = window.location.pathname; if (path === '/signup') return <SignupView onAuthenticated={handleAuthenticated} />; if (path === '/onboarding') return <OnboardingView />; return <LoginView onAuthenticated={handleAuthenticated} /> }
  const currentLabel = nav.find((item) => item.id === view)?.label ?? (view === 'job-details' ? 'Job Details' : view === 'resume-results' ? 'Resume Results' : view === 'customize' ? 'Customize Application' : view === 'interview-prep' ? 'Interview Preparation' : 'Settings')
  return <div className="app-shell"><aside className="sidebar"><div className="brand-mark"><span>AC</span><div><strong>AI Career</strong><small>Companion</small></div></div><div className="workspace-label">STUDENT WORKSPACE</div><nav aria-label="Primary navigation">{nav.map((item) => <button className={`nav-item ${view === item.id ? 'active' : ''}`} key={item.id} onClick={() => go(item.id)}><span className="nav-dot" aria-hidden="true" /><span><strong>{item.label}</strong><small>{item.note}</small></span></button>)}</nav><div className="sidebar-divider" /><button className={`nav-item ${view === 'settings' ? 'active' : ''}`} onClick={() => go('settings')}><span className="nav-dot" aria-hidden="true" /><span><strong>Settings</strong><small>Workspace preferences</small></span></button><div className="sidebar-footer"><span className="status-pulse" /> Career workspace</div></aside><main className="main-content"><header className="topbar"><div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>{currentLabel}</strong></div><div className="account"><div className="avatar">{initials(currentUser?.full_name ?? '')}</div><div><strong>{currentUser?.full_name}</strong><small>{currentUser?.email}</small></div><button className="text-button" onClick={() => void handleLogout()}>Sign out</button></div></header><div className="mobile-nav" aria-label="Mobile navigation">{nav.slice(0, 5).map((item) => <button className={view === item.id ? 'active' : ''} key={item.id} onClick={() => go(item.id)}>{item.label}</button>)}</div><div className="page-wrap">{content}</div></main></div>
}

function LoginView({ onAuthenticated }: { onAuthenticated: (session: AuthSession) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submit = async () => {
    if (!email.includes('@')) { setError('Enter a valid email address.'); return }
    if (!password) { setError('Enter your password.'); return }
    setError('')
    setSubmitting(true)
    try {
      const session = await login({ email, password })
      onAuthenticated(session)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'We could not sign you in. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }
  return <main className="auth-page"><section className="auth-panel"><div className="auth-brand"><span>AC</span><div><strong>AI Career</strong><small>Companion</small></div></div><div className="auth-copy"><p className="eyebrow">STUDENT WORKSPACE</p><h1>Your career context, in one place.</h1><p>Sign in to manage your candidate profile and continue building your career direction.</p></div><form className="auth-form" onSubmit={(event) => { event.preventDefault(); void submit() }}><label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" disabled={submitting} /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" disabled={submitting} /></label>{error && <p className="auth-error" role="alert">{error}</p>}<button className="primary-button auth-submit" disabled={submitting}>{submitting ? 'Signing in...' : 'Sign in'}</button></form><button className="text-button" onClick={() => { window.history.pushState({}, '', '/signup'); window.location.reload() }}>Need an account? Sign up</button></section><aside className="auth-aside"><p className="eyebrow">AI CAREER COMPANION</p><h2>Start with a clearer picture of where you are.</h2><div className="auth-flow"><span>01</span><div><strong>Understand your profile</strong><small>Bring your career context together</small></div></div><div className="auth-flow"><span>02</span><div><strong>Find your direction</strong><small>Explore paths and skill gaps</small></div></div><div className="auth-flow"><span>03</span><div><strong>Keep moving forward</strong><small>Follow a personalized learning path</small></div></div></aside></main>
}

function SignupView({ onAuthenticated }: { onAuthenticated: (session: AuthSession) => void }) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const submit = async () => {
    if (!fullName.trim()) { setError('Enter your full name.'); return }
    if (!email.includes('@')) { setError('Enter a valid email address.'); return }
    if (password.length < 8) { setError('Password must contain at least 8 characters.'); return }
    if (password !== confirmPassword) { setError('Passwords do not match.'); return }
    setError('')
    setSubmitting(true)
    try {
      const session = await registerAccount({ full_name: fullName, email, password, confirm_password: confirmPassword })
      onAuthenticated(session)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'We could not create your account. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }
  return <main className="auth-page"><section className="auth-panel"><div className="auth-brand"><span>AC</span><div><strong>AI Career</strong><small>Companion</small></div></div><div className="auth-copy"><p className="eyebrow">CREATE YOUR WORKSPACE</p><h1>Start with your career context.</h1><p>Create an account, then complete your career profile.</p></div><form className="auth-form" onSubmit={(event) => { event.preventDefault(); void submit() }}><label>Full name<input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Your name" disabled={submitting} /></label><label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" disabled={submitting} /></label><label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" disabled={submitting} /></label><label>Confirm password<input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Re-enter your password" disabled={submitting} /></label>{error && <p className="auth-error" role="alert">{error}</p>}<button className="primary-button auth-submit" disabled={submitting}>{submitting ? 'Creating account...' : 'Create account'}</button></form><button className="text-button" onClick={() => { window.history.pushState({}, '', '/'); window.location.reload() }}>Already have an account? Sign in</button></section><aside className="auth-aside"><p className="eyebrow">YOUR FIRST STEPS</p><h2>Build a profile that can grow with you.</h2><div className="auth-flow"><span>01</span><div><strong>Tell us about your direction</strong><small>Interests and experience</small></div></div><div className="auth-flow"><span>02</span><div><strong>Add your resume</strong><small>Skills and projects extracted</small></div></div></aside></main>
}
function OnboardingView() { return <main className="auth-page"><section className="auth-panel"><div className="auth-brand"><span>AC</span><div><strong>AI Career</strong><small>Companion</small></div></div><div className="auth-copy"><p className="eyebrow">CREATE YOUR ACCOUNT</p><h1>Let's get your workspace set up.</h1><p>Create an account to build your career profile and upload your resume.</p></div><button className="primary-button auth-submit" onClick={() => { window.history.pushState({}, '', '/signup'); window.location.reload() }}>Go to sign up</button></section><aside className="auth-aside"><p className="eyebrow">A CLEAR START</p><h2>Your profile becomes the context behind every next step.</h2><div className="auth-flow"><span>01</span><div><strong>Profile</strong><small>Personal and career details</small></div></div><div className="auth-flow"><span>02</span><div><strong>Guidance</strong><small>Recommendations shaped around you</small></div></div></aside></main> }
function PageHeading({ eyebrow, title, lede, action }: { eyebrow: string; title: string; lede: string; action?: React.ReactNode }) { return <section className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="lede">{lede}</p></div>{action}</section> }
function DashboardView({ currentUser, profile, resumeLifecycle, resumeRestoring, resumeRecord, structuredResume, notice, onNavigate }: {
  currentUser: AuthUser | null
  profile: CandidateProfile | null
  resumeLifecycle: ResumeLifecycle
  resumeRestoring: boolean
  resumeRecord: ResumeRecord | null
  structuredResume: StructuredResume | null
  notice: string
  onNavigate: (view: View) => void
}) {
  const displayName = (currentUser?.full_name ?? '').trim().split(/\s+/)[0] || 'there'
  const heading = `Good ${greetingForTime()}, ${displayName}.`
  const data = structuredResume?.data

  if (resumeRestoring) return <PageHeading eyebrow="DASHBOARD" title={heading} lede="Loading your workspace..." />

  if (resumeLifecycle === 'no_resume') return <><PageHeading eyebrow="DASHBOARD" title={heading} lede="Upload your resume to build your career profile." action={<button className="primary-button" onClick={() => onNavigate('resume')}>Upload resume -&gt;</button>} /><div className="architecture-note" role="status">No resume analyzed yet. No skills extracted yet. No job matches yet.</div></>

  if (resumeLifecycle === 'uploading' || resumeLifecycle === 'processing') return <><PageHeading eyebrow="DASHBOARD" title={heading} lede="Your resume is being processed." /><div className="architecture-note" role="status">{resumeLifecycle === 'uploading' ? 'Uploading' : 'Processing'} {resumeRecord?.original_filename ?? 'your resume'}...</div></>

  if (resumeLifecycle === 'failed') return <><PageHeading eyebrow="DASHBOARD" title={heading} lede="We could not finish processing your resume." action={<button className="primary-button" onClick={() => onNavigate('resume')}>Upload again -&gt;</button>} /><div className="error-notice" role="alert">{notice || 'Resume processing failed.'}</div></>

  return <>
    <PageHeading eyebrow="DASHBOARD" title={heading} lede="Your career profile, built from your latest processed resume." action={<button className="primary-button" onClick={() => onNavigate('resume-results')}>View resume results -&gt;</button>} />
    <section className="dashboard-stats">
      <Stat label="Resume status" value="Processed" detail={resumeRecord?.original_filename ?? ''} />
      <Stat label="Skills extracted" value={String(data?.skills.length ?? 0)} detail="From your latest resume" />
      <Stat label="Education entries" value={String(data?.education.length ?? 0)} detail="From your latest resume" />
      <Stat label="Projects" value={String(data?.projects.length ?? 0)} detail="From your latest resume" />
    </section>
    <div className="dashboard-columns">
      <section>
        <div className="section-heading"><div><p className="eyebrow">EXTRACTED SKILLS</p><h2>From your latest resume</h2></div><button className="text-button" onClick={() => onNavigate('resume-results')}>View all -&gt;</button></div>
        {data && data.skills.length > 0 ? <div className="chip-list">{data.skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div> : <p className="muted">No skills extracted yet.</p>}
      </section>
      <aside className="card dashboard-side">
        <p className="eyebrow">PROFILE</p>
        <h3>{profile?.full_name ?? currentUser?.full_name ?? ''}</h3>
        <p className="muted">{profile?.target_roles && profile.target_roles.length > 0 ? profile.target_roles.join(', ') : 'No target roles saved yet.'}</p>
        <button className="text-button" onClick={() => onNavigate('profile')}>Edit profile -&gt;</button>
      </aside>
    </div>
    <section className="dashboard-columns lower">
      <div className="card activity-card">
        <div className="card-heading"><div><p className="eyebrow">EDUCATION</p></div></div>
        {data && data.education.length > 0 ? data.education.map((item, index) => <p className="result-bullet" key={index}>+ {String(item.raw_text ?? '')}</p>) : <p className="muted">No education extracted yet.</p>}
      </div>
      <div className="card roadmap-summary">
        <p className="eyebrow">EXPERIENCE</p>
        {data && [...data.experience, ...data.internships].length > 0 ? [...data.experience, ...data.internships].map((item, index) => <p className="result-bullet" key={index}>+ {String(item.raw_text ?? '')}</p>) : <p className="muted">No experience extracted yet.</p>}
      </div>
    </section>
  </>
}
function Stat({ label, value, detail }: { label: string; value: string; detail: string }) { return <article className="card stat-card"><p className="eyebrow">{label}</p><strong>{value}</strong><small>{detail}</small></article> }
function CareersView({ resumeId, onOpenJob }: { resumeId: number | null; onOpenJob: (jobId: string) => void }) {
  const [matches, setMatches] = useState<JobMatchResult[] | null>(null)
  const [matchError, setMatchError] = useState('')
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<JobSearchResult[] | null>(null)
  const [searchStatus, setSearchStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [searchError, setSearchError] = useState('')

  useEffect(() => {
    if (resumeId === null) return
    void getJobMatches(resumeId).then(setMatches).catch((reason: unknown) => setMatchError(reason instanceof Error ? reason.message : 'We could not load recommendations.'))
  }, [resumeId])

  const runSearch = async (event: FormEvent) => {
    event.preventDefault()
    if (!query.trim()) return
    setSearchStatus('loading'); setSearchError(''); setSearchResults(null)
    try {
      const results = await searchJobs(query.trim(), 10)
      setSearchResults(results)
      setSearchStatus('idle')
    } catch (error: unknown) {
      setSearchStatus('error')
      setSearchError(error instanceof Error ? error.message : 'We could not search internships. Please try again.')
    }
  }

  return <>
    <PageHeading eyebrow="CAREER RECOMMENDATIONS" title="Paths that fit your profile." lede="Search the internship knowledge base by role, skill or topic, or review recommendations ranked from your latest resume." />
    <section className="card comparison-card">
      <div className="card-heading"><div><p className="eyebrow">SEMANTIC JOB SEARCH</p><h3>Search internships</h3></div></div>
      <form className="assistant-input" onSubmit={(event) => void runSearch(event)}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='e.g. "Python machine learning internship"' aria-label="Search internships" />
        <button className="primary-button" disabled={searchStatus === 'loading'}>{searchStatus === 'loading' ? 'Searching...' : 'Search'}</button>
      </form>
      {searchStatus === 'error' && <div className="error-notice" role="alert">{searchError}</div>}
      {searchStatus !== 'error' && searchResults !== null && searchResults.length === 0 && <p className="muted">No internships matched that search.</p>}
      {searchResults !== null && searchResults.length > 0 && <section className="career-list">
        {searchResults.map((result) => <article className="card career-card" key={result.job_id}>
          <div className="career-card-top"><span className="role-mark">{result.job_title.slice(0, 1)}</span><span className="match-badge">{Math.round(result.similarity_score * 100)}% relevance</span></div>
          <h3>{result.job_title}</h3>
          <p>{result.company} · {result.domain} · {result.location} · {result.work_mode} · {result.employment_type}</p>
          <div className="tag-row">{result.required_skills.slice(0, 4).map((skill) => <span key={skill}>{skill}</span>)}</div>
          <button className="text-button" onClick={() => onOpenJob(result.job_id)}>View job details -&gt;</button>
        </article>)}
      </section>}
    </section>
    <section className="card comparison-card">
      <div className="card-heading"><div><p className="eyebrow">RECOMMENDED FOR YOUR RESUME</p><h3>Ranked from your latest processed resume</h3></div></div>
      {matchError ? <div className="error-notice" role="alert">{matchError}</div>
        : resumeId === null ? <div className="architecture-note">Process a resume to see recommendations ranked for you.</div>
        : matches === null ? <p className="muted">Loading your recommendations...</p>
        : matches.length === 0 ? <p className="muted">No job matches were found for your resume yet.</p>
        : <section className="career-list">{matches.map((match) => <article className="card career-card" key={match.job_id}><div className="career-card-top"><span className="role-mark">{match.job_title.slice(0, 1)}</span><span className="match-badge">{Math.round(match.match_score)}% match</span></div><h3>{match.job_title}</h3><p>{match.company} · {match.domain}</p><div className="tag-row">{match.matched_required_skills.slice(0, 3).map((skill) => <span key={skill}>{skill}</span>)}</div><p className="muted">{match.reasoning}</p><p className="result-bullet">Missing required: {match.missing_required_skills.join(', ') || 'None'}</p><button className="text-button" onClick={() => onOpenJob(match.job_id)}>View job details -&gt;</button></article>)}</section>}
    </section>
  </>
}
function JobDetailsView({ jobId, resumeId, onBack, onAnalyzeSkillGap, onCustomizeApplication, onInterviewPrep }: { jobId: string | null; resumeId: number | null; onBack: () => void; onAnalyzeSkillGap: () => void; onCustomizeApplication: () => void; onInterviewPrep: () => void }) {
  const [job, setJob] = useState<JobPosting | null>(null)
  const [jobError, setJobError] = useState('')
  const [loading, setLoading] = useState(true)
  const [matches, setMatches] = useState<JobMatchResult[] | null>(null)
  const [matchStatus, setMatchStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [matchError, setMatchError] = useState('')

  useEffect(() => {
    setLoading(true); setJobError(''); setJob(null); setMatches(null)
    if (!jobId) { setLoading(false); setJobError('No job was selected.'); return }
    void getJobDetails(jobId).then((result) => { setJob(result); setLoading(false) }).catch((error: unknown) => { setJobError(error instanceof Error ? error.message : 'We could not load this job.'); setLoading(false) })
  }, [jobId])

  const loadMatch = async () => {
    if (!jobId || resumeId === null) return
    setMatchStatus('loading'); setMatchError('')
    try {
      const results = await getJobMatches(resumeId, 20)
      setMatches(results.filter((result) => result.job_id === jobId))
      setMatchStatus('idle')
    } catch (error: unknown) {
      setMatchStatus('error')
      setMatchError(error instanceof Error ? error.message : 'We could not load your match result.')
    }
  }

  if (loading) return <PageHeading eyebrow="JOB DETAILS" title="Loading job details..." lede="" />
  if (jobError || !job) return <><PageHeading eyebrow="JOB DETAILS" title="Job not found." lede={jobError || 'This job could not be loaded.'} action={<button className="text-button" onClick={onBack}>Back to search -&gt;</button>} /></>

  const matchResult = matches?.[0] ?? null

  return <>
    <PageHeading eyebrow="JOB DETAILS" title={job.job_title} lede={`${job.company} · ${job.domain}`} action={<button className="text-button" onClick={onBack}>Back to search -&gt;</button>} />
    <section className="results-grid resume-result-grid">
      <article className="card result-card"><p className="eyebrow">OVERVIEW</p><p className="result-bullet">Location: {job.location}</p><p className="result-bullet">Work mode: {job.work_mode}</p><p className="result-bullet">Employment type: {job.employment_type}</p><p className="result-bullet">Posted: {job.posted_date}</p></article>
      <article className="card result-card"><p className="eyebrow">DESCRIPTION</p><p className="muted">{job.job_description}</p></article>
      <article className="card result-card"><p className="eyebrow">RESPONSIBILITIES</p>{job.responsibilities.map((item, index) => <p className="result-bullet" key={index}>+ {item}</p>)}</article>
      <article className="card result-card"><p className="eyebrow">REQUIRED SKILLS</p><div className="chip-list">{job.required_skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div>{job.preferred_skills.length > 0 && <><p className="muted result-gap-label">Preferred</p><div className="chip-list">{job.preferred_skills.map((skill) => <span key={skill}>{skill}</span>)}</div></>}</article>
      <article className="card result-card"><p className="eyebrow">QUALIFICATIONS</p>{job.qualifications.map((item, index) => <p className="result-bullet" key={index}>+ {item}</p>)}<p className="muted">Experience: {job.experience_requirements}</p><p className="muted">Education: {job.education_requirements}</p></article>
    </section>
    <section className="card comparison-card">
      <div className="card-heading"><div><p className="eyebrow">RESUME MATCH</p><h3>Your match for this role</h3></div>{resumeId !== null && matches === null && <button className="primary-button" onClick={() => void loadMatch()} disabled={matchStatus === 'loading'}>{matchStatus === 'loading' ? 'Checking...' : 'Check my match'}</button>}</div>
      {resumeId === null && <div className="architecture-note">Process a resume to see your match for this role.</div>}
      {matchStatus === 'error' && <div className="error-notice" role="alert">{matchError}</div>}
      {matchResult && <div className="results-grid resume-result-grid"><article className="card result-card"><p className="eyebrow">MATCH SCORE</p><strong>{Math.round(matchResult.match_score)}%</strong><p className="muted">{matchResult.reasoning}</p></article><article className="card result-card"><p className="eyebrow">MATCHED SKILLS</p>{matchResult.matched_required_skills.length > 0 ? <div className="chip-list">{matchResult.matched_required_skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div> : <p className="muted">None</p>}</article><article className="card result-card"><p className="eyebrow">MISSING REQUIRED SKILLS</p>{matchResult.missing_required_skills.length > 0 ? <div className="chip-list">{matchResult.missing_required_skills.map((skill) => <span className="warning-chip" key={skill}>{skill}</span>)}</div> : <p className="muted">None</p>}</article></div>}
      {matches !== null && matches.length === 0 && <p className="muted">This job was not found in your ranked matches. It may not currently be among your top retrieval candidates.</p>}
      {resumeId !== null && <div className="detail-actions"><button className="primary-button" onClick={onAnalyzeSkillGap}>Analyze Skill Gaps -&gt;</button><button className="secondary-button" onClick={onCustomizeApplication}>Customize Application -&gt;</button><button className="secondary-button" onClick={onInterviewPrep}>Prepare for Interview -&gt;</button></div>}
    </section>
  </>
}
const GAP_TONE: Record<GapItem['match_type'], string> = { missing: 'missing', partial: 'needs-improvement', learning_only: 'adequate', demonstrated: 'strong' }
const GAP_LABEL: Record<GapItem['match_type'], string> = { missing: 'Missing', partial: 'Partially demonstrated', learning_only: 'Currently learning / not yet demonstrated', demonstrated: 'Matched' }
function GapCard({ item }: { item: GapItem }) {
  const tone = GAP_TONE[item.match_type]
  const label = GAP_LABEL[item.match_type]
  return <article className="card result-card">
    <div className="card-heading"><strong>{item.requirement}</strong><span className={`skill-status ${tone}`}>{label} · {item.priority}</span></div>
    <p className="muted">{item.importance}</p>
    <p className="result-bullet">{item.student_evidence.length > 0 ? `Evidence: ${item.student_evidence.map((evidence) => evidence.evidence).join(' | ')}` : item.reason}</p>
    <p className="result-bullet">Recommendation: {item.recommendation}</p>
  </article>
}
function GapSection({ eyebrow, subtitle, items }: { eyebrow: string; subtitle: string; items: GapItem[] }) {
  if (items.length === 0) return null
  return <section className="card comparison-card">
    <div className="card-heading"><div><p className="eyebrow">{eyebrow}</p><h3>{subtitle}</h3></div></div>
    <div className="results-grid resume-result-grid">{items.map((item, index) => <GapCard item={item} key={`${item.requirement}-${index}`} />)}</div>
  </section>
}
function SkillsView({ resumeId, jobId, onRoadmap, onSearchJobs, onCustomizeApplication, onInterviewPrep }: { resumeId: number | null; jobId: string | null; onRoadmap: () => void; onSearchJobs: () => void; onCustomizeApplication: () => void; onInterviewPrep: () => void }) {
  const [analysis, setAnalysis] = useState<SkillGapAnalysis | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState('')

  const runAnalysis = (resume: number, job: string, isCurrent: () => boolean = () => true) => {
    setStatus('loading'); setError('')
    void analyzeSkillGap(resume, job)
      .then((result) => { if (isCurrent()) { setAnalysis(result); setStatus('idle') } })
      .catch((reason: unknown) => { if (isCurrent()) { setStatus('error'); setError(reason instanceof Error ? reason.message : 'We could not run your skill gap analysis.') } })
  }

  useEffect(() => {
    let cancelled = false
    setAnalysis(null)
    setError('')
    setStatus('idle')
    if (resumeId !== null && jobId !== null) runAnalysis(resumeId, jobId, () => !cancelled)
    return () => { cancelled = true }
  }, [resumeId, jobId])

  return <>
    <PageHeading eyebrow="SKILL GAP ANALYSIS" title="Understand what to learn next." lede="A grounded comparison of your resume against the internship you selected." action={<button className="primary-button" onClick={onSearchJobs}>Search internships -&gt;</button>} />
    {resumeId === null && <div className="architecture-note">Upload and process your resume before running skill gap analysis.</div>}
    {resumeId !== null && jobId === null && <div className="architecture-note">Select an internship to analyze your skill gaps. Open a job's details and choose "Analyze Skill Gaps".</div>}
    {resumeId !== null && jobId !== null && status === 'loading' && <p className="muted">Analyzing your skill gaps against this internship...</p>}
    {resumeId !== null && jobId !== null && status === 'error' && <div className="error-notice" role="alert">{error}</div>}
    {analysis && <>
      <section className="card comparison-card">
        <div className="card-heading">
          <div><p className="eyebrow">SELECTED INTERNSHIP</p><h3>{analysis.job_title}</h3></div>
          <button className="text-button" onClick={() => resumeId !== null && jobId !== null && runAnalysis(resumeId, jobId)} disabled={status === 'loading'}>Refresh analysis -&gt;</button>
        </div>
        <p className="muted">{analysis.company} · {analysis.domain} · {analysis.location}</p>
        {analysis.stale && <p className="result-bullet">Your profile has changed since this analysis was generated. Refresh for updated results.</p>}
      </section>
      <div className="skill-summary-grid">
        <div className="card skill-score-card">
          <p className="eyebrow">SKILL READINESS</p>
          <strong>{analysis.summary.overall_readiness}%</strong>
          <div className="progress-track"><span style={{ width: `${Math.min(100, analysis.summary.overall_readiness)}%` }} /></div>
          <p className="muted">Required skills matched: {analysis.summary.required_requirements_met}/{analysis.summary.required_requirements_total} &middot; Preferred: {analysis.summary.preferred_requirements_met}/{analysis.summary.preferred_requirements_total}</p>
          <p className="muted">A separate measure from your Milestone 2 job match score — this reflects requirement-by-requirement readiness, not semantic relevance.</p>
        </div>
        <div className="card priority-card">
          <p className="eyebrow">GAP OVERVIEW</p>
          <div className="mini-gap"><span>Critical (required, missing)</span><span>{analysis.summary.critical_gap_count}</span></div>
          <div className="mini-gap"><span>Partially demonstrated</span><span>{analysis.summary.partial_gap_count}</span></div>
          <div className="mini-gap"><span>Preferred gaps</span><span>{analysis.summary.preferred_gap_count}</span></div>
          <div className="mini-gap"><span>Experience gaps</span><span>{analysis.summary.experience_gap_count}</span></div>
          <div className="mini-gap"><span>Qualification gaps</span><span>{analysis.summary.qualification_gap_count}</span></div>
        </div>
      </div>
      <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">STRENGTHS</p><h3>What you already demonstrate</h3></div></div>
        {analysis.strengths.length === 0 ? <p className="muted">No confirmed strengths were found for this role yet.</p> : <div className="results-grid resume-result-grid">
          {analysis.strengths.map((item, index) => <article className="card result-card" key={`${item.requirement}-${index}`}>
            <div className="card-heading"><strong>{item.requirement}</strong><span className="skill-status strong">Matched</span></div>
            <p className="muted">{item.reason}</p>
            {item.evidence.length > 0 && <p className="result-bullet">Evidence: {item.evidence.map((evidence) => evidence.evidence).join(' | ')}</p>}
          </article>)}
        </div>}
      </section>
      {analysis.summary.critical_gap_count === 0 && analysis.summary.partial_gap_count === 0 && <div className="success-notice" role="status">You meet every required skill extracted for this role. Review preferred skills and qualifications below to strengthen your application further.</div>}
      <GapSection eyebrow="CRITICAL GAPS" subtitle="Required skills with no evidence found in your resume/profile" items={analysis.critical_gaps} />
      <GapSection eyebrow="PARTIALLY DEMONSTRATED" subtitle="Related evidence exists, but the requirement is not fully confirmed" items={analysis.partial_gaps} />
      <GapSection eyebrow="PREFERRED SKILL GAPS" subtitle="Not mandatory, but would strengthen your application" items={analysis.preferred_gaps} />
      <GapSection eyebrow="EXPERIENCE GAPS" subtitle="What this role expects beyond what your resume currently shows" items={analysis.experience_gaps} />
      <GapSection eyebrow="QUALIFICATION GAPS" subtitle="Education and other stated qualifications" items={analysis.qualification_gaps} />
      {analysis.recommendations.length > 0 && <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">IMPROVEMENT PLAN</p><h3>Ordered by priority</h3></div></div>
        {analysis.recommendations.map((item, index) => <div className="recommendation-line" key={`${item.requirement}-${index}`}>
          <span>{item.priority}</span>
          <div><strong>{item.requirement}</strong><p className="muted">{item.recommendation}</p></div>
        </div>)}
      </section>}
      <div className="detail-actions"><button className="primary-button" onClick={onCustomizeApplication}>Customize Application -&gt;</button><button className="secondary-button" onClick={onInterviewPrep}>Prepare for Interview -&gt;</button><button className="secondary-button" onClick={onRoadmap}>View learning roadmap</button></div>
    </>}
  </>
}

const KEYWORD_TONE: Record<KeywordStatus, string> = { unsupported: 'missing', partial: 'needs-improvement', supported: 'strong' }
const KEYWORD_LABEL: Record<KeywordStatus, string> = { unsupported: 'Unsupported', partial: 'Partially supported', supported: 'Supported' }

function bulletDraftsFrom(resume: TailoredResume): Record<string, string> {
  const drafts: Record<string, string> = {}
  for (const project of resume.projects) drafts[project.source_path] = project.tailored_text
  for (const bullet of [...resume.experience, ...resume.internships]) drafts[bullet.source_path] = bullet.tailored_text
  return drafts
}

function ProvenanceDetails({ evidenceIds, evidenceById }: { evidenceIds: string[]; evidenceById: Record<string, EvidenceRecord> }) {
  if (evidenceIds.length === 0) return null
  return <details className="provenance-details">
    <summary>Supported by ({evidenceIds.length})</summary>
    <ul className="result-list">
      {evidenceIds.map((id) => {
        const record = evidenceById[id]
        if (!record) return null
        return <li key={id}><span>{record.source_name}</span><small className="muted">{record.raw_text.length > 140 ? `${record.raw_text.slice(0, 140)}...` : record.raw_text}</small></li>
      })}
    </ul>
  </details>
}

function BulletComparison({ original, tailored, draft, sourcePath, jobKeywordsUsed, evidenceIds, evidenceById, onEdit }: {
  original: string
  tailored: string
  draft: string
  sourcePath: string
  jobKeywordsUsed: string[]
  evidenceIds: string[]
  evidenceById: Record<string, EvidenceRecord>
  onEdit: (sourcePath: string, value: string) => void
}) {
  const edited = draft !== tailored
  return <div className="bullet-comparison">
    {original !== tailored && <p className="muted"><strong>Original:</strong> {original}</p>}
    <label className="muted"><strong>Tailored{edited ? ' (editing)' : ''}:</strong>
      <textarea className="cover-letter-editor bullet-editor" value={draft} onChange={(event) => onEdit(sourcePath, event.target.value)} rows={2} />
    </label>
    {jobKeywordsUsed.length > 0 && <div className="tag-row">{jobKeywordsUsed.map((keyword) => <span key={keyword}>{keyword}</span>)}</div>}
    <ProvenanceDetails evidenceIds={evidenceIds} evidenceById={evidenceById} />
  </div>
}

const GENERATION_LABEL: Record<GenerationMode, string> = { llm: 'AI Enhanced', deterministic_fallback: 'Grounded Fallback' }
const GENERATION_TONE: Record<GenerationMode, string> = { llm: 'strong', deterministic_fallback: 'adequate' }

function CustomizeView({ resumeId, jobId, structuredResume, onSearchJobs, onInterviewPrep }: {
  resumeId: number | null
  jobId: string | null
  structuredResume: StructuredResume | null
  onSearchJobs: () => void
  onInterviewPrep: () => void
}) {
  const [customization, setCustomization] = useState<ApplicationCustomization | null>(null)
  const [versions, setVersions] = useState<ApplicationCustomizationSummary[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState('')
  const [summaryDraft, setSummaryDraft] = useState('')
  const [coverLetterDraft, setCoverLetterDraft] = useState('')
  const [bulletDrafts, setBulletDrafts] = useState<Record<string, string>>({})
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [exportError, setExportError] = useState('')
  const [exporting, setExporting] = useState('')

  const applyResult = (result: ApplicationCustomization) => {
    setCustomization(result)
    setSummaryDraft(result.tailored_resume.summary)
    setCoverLetterDraft(result.cover_letter_text)
    setBulletDrafts(bulletDraftsFrom(result.tailored_resume))
    setSaveStatus('idle')
  }

  useEffect(() => {
    let cancelled = false
    setCustomization(null); setVersions([]); setError(''); setStatus('idle')
    if (resumeId === null || jobId === null) return
    void listCustomizations(resumeId, jobId).then(async (list) => {
      if (cancelled) return
      setVersions(list)
      const latest = list[0]
      if (!latest) return
      const full = await getCustomization(resumeId, latest.id)
      if (!cancelled && full) applyResult(full)
    }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'We could not load application customizations.') })
    return () => { cancelled = true }
  }, [resumeId, jobId])

  const generate = async () => {
    if (resumeId === null || jobId === null) return
    setStatus('loading'); setError('')
    try {
      const result = await generateCustomization(resumeId, jobId)
      applyResult(result)
      setVersions(await listCustomizations(resumeId, jobId))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not generate application materials for this resume and internship.')
    }
  }

  const regenerate = async () => {
    if (resumeId === null || customization === null) return
    setStatus('loading'); setError('')
    try {
      const result = await regenerateCustomization(resumeId, customization.id)
      applyResult(result)
      setVersions(await listCustomizations(resumeId, customization.job_id))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not regenerate application materials.')
    }
  }

  const selectVersion = async (id: number) => {
    if (resumeId === null) return
    const full = await getCustomization(resumeId, id)
    if (full) applyResult(full)
  }

  const editBullet = (sourcePath: string, value: string) => setBulletDrafts((drafts) => ({ ...drafts, [sourcePath]: value }))

  const saveEdits = async () => {
    if (resumeId === null || customization === null) return
    // Only send a field/bullet if its draft actually differs from the loaded
    // content — otherwise an untouched field would be marked "user edited" on
    // every save, even though the user never changed it.
    const payload: { summary?: string; cover_letter_text?: string; bullet_edits?: Record<string, string> } = {}
    if (summaryDraft !== customization.tailored_resume.summary) payload.summary = summaryDraft
    if (coverLetterDraft !== customization.cover_letter_text) payload.cover_letter_text = coverLetterDraft
    const loadedBullets = bulletDraftsFrom(customization.tailored_resume)
    const bulletEdits: Record<string, string> = {}
    for (const [sourcePath, draft] of Object.entries(bulletDrafts)) {
      if (draft !== loadedBullets[sourcePath]) bulletEdits[sourcePath] = draft
    }
    if (Object.keys(bulletEdits).length > 0) payload.bullet_edits = bulletEdits
    if (Object.keys(payload).length === 0) { setSaveStatus('saved'); return }
    setSaveStatus('saving')
    try {
      const updated = await updateCustomization(resumeId, customization.id, payload)
      applyResult(updated)
      setSaveStatus('saved')
    } catch (err: unknown) {
      setSaveStatus('idle')
      setError(err instanceof Error ? err.message : 'We could not save your edits.')
    }
  }

  const download = async (docType: ExportDocument, format: ExportFormat) => {
    if (resumeId === null || customization === null) return
    setExportError(''); setExporting(`${docType}-${format}`)
    try {
      await downloadExport(resumeId, customization.id, docType, format)
    } catch (err: unknown) {
      setExportError(err instanceof Error ? err.message : 'We could not export this document.')
    } finally {
      setExporting('')
    }
  }

  if (resumeId === null) return <><PageHeading eyebrow="CUSTOMIZE APPLICATION" title="Tailor your resume and cover letter." lede="Upload and process your resume before customizing an application." /><div className="architecture-note">Upload and process your resume before customizing an application.</div></>
  if (jobId === null) return <><PageHeading eyebrow="CUSTOMIZE APPLICATION" title="Tailor your resume and cover letter." lede="Select an internship to customize your application." action={<button className="primary-button" onClick={onSearchJobs}>Search internships -&gt;</button>} /><div className="architecture-note">Open a job's details or your skill gap analysis and choose "Customize Application" to get started.</div></>

  const resume = customization?.tailored_resume ?? null
  const original = structuredResume?.data ?? null
  const evidenceById: Record<string, EvidenceRecord> = {}
  if (customization) for (const record of customization.evidence) evidenceById[record.evidence_id] = record

  return <>
    <PageHeading
      eyebrow="CUSTOMIZE APPLICATION"
      title={customization ? `Tailored for ${customization.job_title}` : 'Generate a tailored application.'}
      lede={customization ? `${customization.company} · version ${customization.version}${customization.stale ? ' · your resume has changed since this was generated' : ''}` : 'Every claim is grounded in your actual resume and profile — nothing here is invented.'}
      action={customization
        ? <button className="secondary-button" onClick={() => void regenerate()} disabled={status === 'loading'}>{status === 'loading' ? 'Regenerating...' : 'Regenerate ->'}</button>
        : <button className="primary-button" onClick={() => void generate()} disabled={status === 'loading'}>{status === 'loading' ? 'Generating...' : 'Generate tailored application ->'}</button>}
    />
    {status === 'loading' && <p className="muted">{customization ? 'Regenerating your tailored application...' : 'Generating your tailored application...'}</p>}
    {status === 'error' && <div className="error-notice" role="alert">{error}</div>}

    {versions.length > 1 && <div className="tag-row">{versions.map((item) => <span key={item.id}><button className={`text-button ${customization?.id === item.id ? 'active' : ''}`} onClick={() => void selectVersion(item.id)}>v{item.version} · {GENERATION_LABEL[item.generation_mode]}{item.stale ? ' (stale)' : ''}</button></span>)}</div>}

    {customization && <>
      <div className="mini-gap">
        <span className={`skill-status ${GENERATION_TONE[customization.generation.mode]}`}>{GENERATION_LABEL[customization.generation.mode]}</span>
        <span className="muted">
          {customization.generation.mode === 'llm'
            ? `Rewritten by ${customization.generation.provider ?? 'an LLM'}${customization.generation.model ? ` (${customization.generation.model})` : ''}, validated against your evidence.`
            : customization.generation.attempted_llm
              ? 'AI enhancement unavailable or failed validation. A grounded fallback version is shown.'
              : 'No LLM provider is configured — this is the deterministic, template-based version.'}
        </span>
      </div>

      {customization.parser_warning_notice && <div className="architecture-note" role="status">{customization.parser_warning_notice}</div>}
      {customization.validation.passed
        ? <div className="success-notice" role="status">Grounding check passed — every generated claim traces to your actual resume/profile.</div>
        : <div className="error-notice" role="alert"><strong>Grounding warnings found.</strong><ul>{customization.validation.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}

      <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">KEYWORD ALIGNMENT</p><h3>How your resume matches this role's skills</h3></div></div>
        {(['supported', 'partial', 'unsupported'] as KeywordStatus[]).map((statusKey) => {
          const items = customization.keyword_classification.filter((item) => item.status === statusKey)
          if (items.length === 0) return null
          return <div className="mini-gap" key={statusKey}>
            <span className={`skill-status ${KEYWORD_TONE[statusKey]}`}>{KEYWORD_LABEL[statusKey]}</span>
            <span className="chip-list">{items.map((item) => <span className={statusKey === 'unsupported' ? 'warning-chip' : 'skill-chip'} key={item.keyword}>{item.keyword}</span>)}</span>
          </div>
        })}
        <p className="muted">Unsupported keywords are never added to your resume or cover letter — only skills you can already demonstrate are used.</p>
      </section>

      {resume && <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">PROFESSIONAL SUMMARY</p><h3>Tailored, editable</h3></div></div>
        <textarea className="cover-letter-editor" value={summaryDraft} onChange={(event) => setSummaryDraft(event.target.value)} rows={3} />
        {customization.user_edits.edited_fields.includes('summary') && <p className="muted">User edited — no longer treated as an AI-generated, evidence-verified claim.</p>}
        <ProvenanceDetails evidenceIds={resume.summary_sources.flatMap((path) => customization.evidence.filter((e) => e.source_path === path).map((e) => e.evidence_id))} evidenceById={evidenceById} />
      </section>}

      {resume && original && <section className="results-grid resume-result-grid">
        <article className="card result-card">
          <p className="eyebrow">SKILLS — ORIGINAL ORDER</p>
          <div className="chip-list">{original.skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div>
        </article>
        <article className="card result-card">
          <p className="eyebrow">SKILLS — REORDERED FOR THIS ROLE</p>
          <div className="chip-list">{resume.skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div>
        </article>
      </section>}

      {resume && resume.projects.length > 0 && <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">PROJECTS</p><h3>Ranked by relevance to this role — original vs. tailored</h3></div></div>
        <div className="results-grid resume-result-grid">
          {resume.projects.map((project) => <article className="card result-card" key={project.source_path}>
            <div className="card-heading"><strong>{project.title}</strong><span className="skill-status strong">Rank #{project.relevance_rank}</span></div>
            <BulletComparison
              original={project.original_text} tailored={project.tailored_text} draft={bulletDrafts[project.source_path] ?? project.tailored_text}
              sourcePath={project.source_path} jobKeywordsUsed={project.job_keywords_used} evidenceIds={project.evidence_ids}
              evidenceById={evidenceById} onEdit={editBullet}
            />
          </article>)}
        </div>
      </section>}

      {resume && (resume.experience.length > 0 || resume.internships.length > 0) && <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">EXPERIENCE AND INTERNSHIPS</p><h3>Original vs. tailored</h3></div></div>
        {[...resume.experience, ...resume.internships].map((bullet) => <BulletComparison
          key={bullet.source_path}
          original={bullet.original_text} tailored={bullet.tailored_text} draft={bulletDrafts[bullet.source_path] ?? bullet.tailored_text}
          sourcePath={bullet.source_path} jobKeywordsUsed={bullet.job_keywords_used} evidenceIds={bullet.evidence_ids}
          evidenceById={evidenceById} onEdit={editBullet}
        />)}
      </section>}

      <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">COVER LETTER</p><h3>Tailored, editable</h3></div></div>
        <textarea className="cover-letter-editor" value={coverLetterDraft} onChange={(event) => setCoverLetterDraft(event.target.value)} rows={10} />
        {customization.user_edits.edited_fields.includes('cover_letter_text') && <p className="muted">User edited — no longer treated as an AI-generated, evidence-verified claim.</p>}
        <ProvenanceDetails evidenceIds={[...new Set(customization.cover_letter.flatMap((s) => s.evidence_ids))]} evidenceById={evidenceById} />
      </section>

      <div className="detail-actions">
        <button className="primary-button" onClick={() => void saveEdits()} disabled={saveStatus === 'saving'}>{saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved' : 'Save edits'}</button>
        <button className="secondary-button" onClick={() => void download('resume', 'pdf')} disabled={exporting !== ''}>{exporting === 'resume-pdf' ? 'Exporting...' : 'Export resume (PDF)'}</button>
        <button className="secondary-button" onClick={() => void download('resume', 'docx')} disabled={exporting !== ''}>{exporting === 'resume-docx' ? 'Exporting...' : 'Export resume (DOCX)'}</button>
        <button className="secondary-button" onClick={() => void download('cover_letter', 'pdf')} disabled={exporting !== ''}>{exporting === 'cover_letter-pdf' ? 'Exporting...' : 'Export cover letter (PDF)'}</button>
        <button className="secondary-button" onClick={() => void download('cover_letter', 'docx')} disabled={exporting !== ''}>{exporting === 'cover_letter-docx' ? 'Exporting...' : 'Export cover letter (DOCX)'}</button>
        <button className="secondary-button" onClick={onInterviewPrep}>Prepare for Interview -&gt;</button>
      </div>
      {exportError && <div className="error-notice" role="alert">{exportError}</div>}
    </>}
  </>
}

const CATEGORY_ORDER: QuestionCategory[] = ['technical', 'resume', 'project', 'role', 'hr', 'skill_gap']
const CATEGORY_LABEL: Record<QuestionCategory, string> = { technical: 'Technical', resume: 'Resume-based', project: 'Project-based', role: 'Role-specific', hr: 'HR / Behavioral', skill_gap: 'Skill-gap-focused' }
const DIFFICULTY_TONE: Record<Difficulty, string> = { easy: 'adequate', medium: 'needs-improvement', hard: 'missing' }
const PRIORITY_TONE: Record<RevisionPriority, string> = { high: 'missing', medium: 'needs-improvement', low: 'adequate' }

function InterviewQuestionCard({ question, index, evidenceById, mockState, onStartMock, onAnswerChange, onSubmitMock }: {
  question: InterviewQuestion
  index: number
  evidenceById: Record<string, EvidenceRecord>
  mockState: { draft: string; submitting: boolean; error: string; result: MockAnswerEvaluation | null } | undefined
  onStartMock: (index: number) => void
  onAnswerChange: (index: number, value: string) => void
  onSubmitMock: (index: number) => void
}) {
  return <details className="card result-card interview-question-card">
    <summary><span className={`skill-status ${DIFFICULTY_TONE[question.difficulty]}`}>{question.difficulty}</span> {question.question}</summary>
    <div className="mini-gap"><span className="muted">Why this is asked</span></div>
    <p className="muted">{question.why_asked}</p>
    <div className="mini-gap"><span className="muted">What the interviewer is testing</span></div>
    <p className="muted">{question.what_interviewer_is_testing}</p>
    <div className="mini-gap"><span className="muted">How to prepare</span></div>
    <p className="result-bullet">{question.preparation_guidance}</p>
    {question.topics_to_review.length > 0 && <div className="chip-list">{question.topics_to_review.map((topic) => <span className="skill-chip" key={topic}>{topic}</span>)}</div>}
    {question.source_requirements.length > 0 && <div className="tag-row">{question.source_requirements.map((req) => <span key={req}>{req}</span>)}</div>}
    <ProvenanceDetails evidenceIds={question.source_evidence_ids} evidenceById={evidenceById} />
    <div className="mock-interview-block">
      {mockState === undefined
        ? <button className="text-button" onClick={() => onStartMock(index)}>Practice this question -&gt;</button>
        : <>
          <textarea className="cover-letter-editor" value={mockState.draft} onChange={(event) => onAnswerChange(index, event.target.value)} rows={4} placeholder="Type your answer..." />
          <button className="secondary-button" onClick={() => onSubmitMock(index)} disabled={mockState.submitting || !mockState.draft.trim()}>{mockState.submitting ? 'Evaluating...' : 'Submit answer for feedback'}</button>
          {mockState.error && <div className="error-notice" role="alert">{mockState.error}</div>}
          {mockState.result && <div className="mini-gap-block">
            <span className={`skill-status ${GENERATION_TONE[mockState.result.generation.mode]}`}>{GENERATION_LABEL[mockState.result.generation.mode]}</span>
            <p className="result-bullet">{mockState.result.grounded_feedback}</p>
            <p className="muted">Suggested structure: {mockState.result.suggested_structure}</p>
            {mockState.result.strengths.length > 0 && <p className="result-bullet">Strengths: {mockState.result.strengths.join(' ')}</p>}
            {mockState.result.improvements.length > 0 && <p className="result-bullet">To improve: {mockState.result.improvements.join(' ')}</p>}
            {mockState.result.missing_points.length > 0 && <p className="result-bullet">Consider addressing: {mockState.result.missing_points.join(', ')}</p>}
          </div>}
        </>}
    </div>
  </details>
}

function InterviewPrepView({ resumeId, jobId, structuredResume, onSearchJobs }: {
  resumeId: number | null
  jobId: string | null
  structuredResume: StructuredResume | null
  onSearchJobs: () => void
}) {
  const [prep, setPrep] = useState<InterviewPreparation | null>(null)
  const [versions, setVersions] = useState<InterviewPreparationSummary[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState('')
  const [mockAnswers, setMockAnswers] = useState<Record<number, { draft: string; submitting: boolean; error: string; result: MockAnswerEvaluation | null }>>({})

  useEffect(() => {
    let cancelled = false
    setPrep(null); setVersions([]); setError(''); setStatus('idle'); setMockAnswers({})
    if (resumeId === null || jobId === null) return
    void listInterviewPreparations(resumeId, jobId).then(async (list) => {
      if (cancelled) return
      setVersions(list)
      const latest = list[0]
      if (!latest) return
      const full = await getInterviewPreparation(resumeId, latest.id)
      if (!cancelled && full) setPrep(full)
    }).catch((reason: unknown) => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'We could not load interview preparation.') })
    return () => { cancelled = true }
  }, [resumeId, jobId])

  const generate = async () => {
    if (resumeId === null || jobId === null) return
    setStatus('loading'); setError(''); setMockAnswers({})
    try {
      const result = await generateInterviewPreparation(resumeId, jobId)
      setPrep(result)
      setVersions(await listInterviewPreparations(resumeId, jobId))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not generate interview preparation for this resume and internship.')
    }
  }

  const regenerate = async () => {
    if (resumeId === null || prep === null) return
    setStatus('loading'); setError(''); setMockAnswers({})
    try {
      const result = await regenerateInterviewPreparation(resumeId, prep.id)
      setPrep(result)
      setVersions(await listInterviewPreparations(resumeId, prep.job_id))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not regenerate interview preparation.')
    }
  }

  const selectVersion = async (id: number) => {
    if (resumeId === null) return
    const full = await getInterviewPreparation(resumeId, id)
    if (full) { setPrep(full); setMockAnswers({}) }
  }

  const startMock = (index: number) => setMockAnswers((current) => ({ ...current, [index]: current[index] ?? { draft: '', submitting: false, error: '', result: null } }))
  const changeMockAnswer = (index: number, value: string) => setMockAnswers((current) => ({ ...current, [index]: { ...(current[index] ?? { draft: '', submitting: false, error: '', result: null }), draft: value } }))
  const submitMock = async (index: number) => {
    if (resumeId === null || prep === null) return
    const entry = mockAnswers[index]
    if (!entry || !entry.draft.trim()) return
    setMockAnswers((current) => ({ ...current, [index]: { ...entry, submitting: true, error: '' } }))
    try {
      const result = await submitMockAnswer(resumeId, prep.id, index, entry.draft.trim())
      setMockAnswers((current) => ({ ...current, [index]: { ...entry, submitting: false, result } }))
    } catch (err: unknown) {
      setMockAnswers((current) => ({ ...current, [index]: { ...entry, submitting: false, error: err instanceof Error ? err.message : 'We could not evaluate this answer.' } }))
    }
  }

  if (resumeId === null) return <><PageHeading eyebrow="INTERVIEW PREPARATION" title="Prepare for your interview." lede="Upload and process your resume before preparing for an interview." /><div className="architecture-note">Upload and process your resume before preparing for an interview.</div></>
  if (jobId === null) return <><PageHeading eyebrow="INTERVIEW PREPARATION" title="Prepare for your interview." lede="Select an internship to prepare for its interview." action={<button className="primary-button" onClick={onSearchJobs}>Search internships -&gt;</button>} /><div className="architecture-note">Open a job's details, skill gap analysis, or customized application and choose "Prepare for Interview" to get started.</div></>

  const evidenceById: Record<string, EvidenceRecord> = {}
  if (prep) for (const record of prep.evidence) evidenceById[record.evidence_id] = record
  const structuredWarnings = structuredResume?.data.parser_warnings ?? []

  return <>
    <PageHeading
      eyebrow="INTERVIEW PREPARATION"
      title={prep ? `Preparing for ${prep.job_title}` : 'Generate your interview preparation.'}
      lede={prep ? `${prep.company} · version ${prep.version}${prep.stale ? ' · your resume has changed since this was generated' : ''}` : 'Categorized questions, preparation guidance and a revision plan grounded in your actual resume, profile and skill gaps.'}
      action={prep
        ? <button className="secondary-button" onClick={() => void regenerate()} disabled={status === 'loading'}>{status === 'loading' ? 'Regenerating...' : 'Regenerate ->'}</button>
        : <button className="primary-button" onClick={() => void generate()} disabled={status === 'loading'}>{status === 'loading' ? 'Generating...' : 'Generate interview preparation ->'}</button>}
    />
    {status === 'loading' && <p className="muted">{prep ? 'Regenerating your interview preparation...' : 'Generating your interview preparation...'}</p>}
    {status === 'error' && <div className="error-notice" role="alert">{error}</div>}
    {structuredWarnings.length > 0 && <div className="architecture-note" role="status">Your resume was processed with parsing warnings — double-check resume-based questions below against your actual resume.</div>}

    {versions.length > 1 && <div className="tag-row">{versions.map((item) => <span key={item.id}><button className={`text-button ${prep?.id === item.id ? 'active' : ''}`} onClick={() => void selectVersion(item.id)}>v{item.version} · {GENERATION_LABEL[item.generation_mode]}{item.stale ? ' (stale)' : ''}</button></span>)}</div>}

    {prep && <>
      <div className="mini-gap">
        <span className={`skill-status ${GENERATION_TONE[prep.generation.mode]}`}>{GENERATION_LABEL[prep.generation.mode]}</span>
        <span className="muted">
          {prep.generation.mode === 'llm'
            ? `Refined by ${prep.generation.provider ?? 'an LLM'}${prep.generation.model ? ` (${prep.generation.model})` : ''}, validated against your evidence.`
            : prep.generation.attempted_llm
              ? 'AI enhancement unavailable or failed validation. A grounded fallback version is shown.'
              : 'No LLM provider is configured — this is the deterministic, template-based version.'}
        </span>
      </div>

      {prep.parser_warning_notice && <div className="architecture-note" role="status">{prep.parser_warning_notice}</div>}
      {prep.validation.passed
        ? <div className="success-notice" role="status">Grounding check passed — every question traces to your actual resume/profile, the real job requirements, or your Skill Gap Analysis.</div>
        : <div className="error-notice" role="alert"><strong>Grounding warnings found.</strong><ul>{prep.validation.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}

      <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">PREPARATION SUMMARY</p><h3>Overview</h3></div></div>
        <p className="muted">{prep.preparation_summary}</p>
      </section>

      {CATEGORY_ORDER.map((category) => {
        const questions = prep.questions.map((question, index) => ({ question, index })).filter((item) => item.question.category === category)
        if (questions.length === 0) return null
        return <section className="card comparison-card" key={category}>
          <div className="card-heading"><div><p className="eyebrow">{CATEGORY_LABEL[category]}</p><h3>{questions.length} question{questions.length === 1 ? '' : 's'}</h3></div></div>
          <div className="results-grid resume-result-grid">
            {questions.map(({ question, index }) => <InterviewQuestionCard
              key={index} question={question} index={index} evidenceById={evidenceById}
              mockState={mockAnswers[index]} onStartMock={startMock} onAnswerChange={changeMockAnswer} onSubmitMock={(i) => void submitMock(i)}
            />)}
          </div>
        </section>
      })}

      {prep.revision_plan.length > 0 && <section className="card comparison-card">
        <div className="card-heading"><div><p className="eyebrow">REVISION PLAN</p><h3>Ordered by priority</h3></div></div>
        {prep.revision_plan.map((item, index) => <div className="recommendation-line" key={`${item.topic}-${index}`}>
          <span className={`skill-status ${PRIORITY_TONE[item.priority]}`}>{item.priority}</span>
          <div><strong>{item.topic}</strong><p className="muted">{item.reason}</p><p className="result-bullet">{item.suggested_revision}</p><p className="muted">Suggested focus: {item.estimated_focus}</p></div>
        </div>)}
      </section>}
    </>}
  </>
}

function RoadmapView({ resumeId }: { resumeId: number | null }) {
  const [matches, setMatches] = useState<JobMatchResult[] | null>(null)
  useEffect(() => {
    if (resumeId === null) return
    void getJobMatches(resumeId, 1).then(setMatches).catch(() => setMatches([]))
  }, [resumeId])
  const top = matches?.[0] ?? null
  return <>
    <PageHeading eyebrow="LEARNING ROADMAP" title="A path from gaps to capability." lede="Your personalized learning roadmap will appear here after roadmap generation is available." />
    <div className="architecture-note">Your personalized learning roadmap will appear here after roadmap generation is available.</div>
    {top && top.missing_required_skills.length > 0 && <section className="card comparison-card"><div className="card-heading"><div><p className="eyebrow">CURRENT SKILL GAP CONTEXT</p><h3>From your top job match, for reference</h3></div></div><div className="chip-list">{top.missing_required_skills.map((skill) => <span className="warning-chip" key={skill}>{skill}</span>)}</div></section>}
  </>
}
function AssistantView({ profile, resumeLifecycle, structuredResume, onNavigate }: { profile: CandidateProfile | null; resumeLifecycle: ResumeLifecycle; structuredResume: StructuredResume | null; onNavigate: (view: View) => void }) {
  const [messages, setMessages] = useState<{ from: 'user' | 'assistant'; text: string }[]>([])
  const [input, setInput] = useState('')
  const NOT_AVAILABLE = 'AI guidance is planned for a later milestone. This assistant cannot answer yet.'
  const ask = (prompt: string) => setMessages((items) => [...items, { from: 'user', text: prompt }, { from: 'assistant', text: NOT_AVAILABLE }])
  const contextLine = resumeLifecycle === 'processed' && structuredResume
    ? `${structuredResume.data.skills.length} skills extracted from your latest resume`
    : profile && profile.target_roles.length > 0
      ? `Target roles: ${profile.target_roles.join(', ')}`
      : 'No resume or profile context available yet'
  return <><PageHeading eyebrow="AI CAREER ASSISTANT" title="Guidance grounded in your profile." lede="Ask about your resume, target role, skill gaps or learning path." /><div className="assistant-layout"><section className="card assistant-panel"><div className="assistant-context"><span className="mini-icon">AI</span><div><strong>Career context</strong><small>{contextLine}</small></div></div><div className="message-list">{messages.length === 0 && <div className="assistant-empty"><span className="assistant-mark">AC</span><h3>{NOT_AVAILABLE}</h3></div>}{messages.map((message, index) => <div className={`message ${message.from}`} key={`${message.text}-${index}`}><span>{message.from === 'user' ? 'You' : 'AC'}</span><p>{message.text}</p></div>)}</div><form className="assistant-input" onSubmit={(event) => { event.preventDefault(); if (input.trim()) { ask(input); setInput('') } }}><input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about your next step..." aria-label="Ask the career assistant" /><button className="primary-button">Send</button></form></section><aside className="assistant-quick card"><p className="eyebrow">QUICK QUESTIONS</p>{['Analyze my career profile', 'What should I learn next?', 'Explain my skill gaps', 'Explain my resume feedback'].map((prompt) => <button key={prompt} onClick={() => ask(prompt)}>{prompt}<span>-&gt;</span></button>)}<div className="aside-divider" /><p className="eyebrow">RELATED VIEWS</p><button onClick={() => onNavigate('skills')}>View skill gap <span>-&gt;</span></button><button onClick={() => onNavigate('roadmap')}>Open roadmap <span>-&gt;</span></button></aside></div></>
}
function ProgressView({ profile, resumeLifecycle, structuredResume }: { profile: CandidateProfile | null; resumeLifecycle: ResumeLifecycle; structuredResume: StructuredResume | null }) {
  const completionFields = profile ? [profile.full_name, profile.email, profile.education, profile.degree, profile.specialization, profile.experience_level, profile.career_interests.length, profile.target_roles.length, profile.skills.length, profile.career_goals] : []
  const profileCompletion = profile ? Math.round(completionFields.filter(Boolean).length / completionFields.length * 100) : null
  const data = structuredResume?.data
  const resumeAnalyzed = resumeLifecycle === 'processed'
  return <>
    <PageHeading eyebrow="PROGRESS TRACKER" title="See your development clearly." lede="A focused view of what has genuinely been completed so far." />
    <section className="dashboard-stats">
      <Stat label="Profile completion" value={profileCompletion === null ? 'N/A' : `${profileCompletion}%`} detail={profile ? 'Calculated from your saved profile' : 'Profile not loaded yet'} />
      <Stat label="Resume analyzed" value={resumeAnalyzed ? 'Yes' : 'No'} detail={resumeAnalyzed ? 'Structured resume on file' : 'No resume processed yet'} />
      <Stat label="Skills extracted" value={String(data?.skills.length ?? 0)} detail="From your latest resume" />
      <Stat label="Projects extracted" value={String(data?.projects.length ?? 0)} detail="From your latest resume" />
    </section>
    <div className="architecture-note">Roadmap progress not available yet.</div>
  </>
}
function ProfileView({ profile, onProfileSaved }: { profile: CandidateProfile | null; onProfileSaved: (profile: CandidateProfile) => void }) {
  const emptyProfile: CandidateProfilePayload = { full_name: '', email: '', education: null, degree: null, specialization: null, experience_level: null, career_interests: [], target_roles: [], skills: [], career_goals: null }
  const toPayload = (source: CandidateProfile): CandidateProfilePayload => { const { id, created_at, updated_at, ...fields } = source; void id; void created_at; void updated_at; return fields }
  const [form, setForm] = useState<CandidateProfilePayload>(() => profile ? toPayload(profile) : emptyProfile)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  useEffect(() => { setForm(profile ? toPayload(profile) : emptyProfile) }, [profile])
  const updateText = (field: keyof CandidateProfilePayload) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => { setForm({ ...form, [field]: event.target.value || null }); setStatus('idle'); setMessage('') }
  const updateList = (field: 'career_interests' | 'target_roles' | 'skills') => (event: ChangeEvent<HTMLInputElement>) => { setForm({ ...form, [field]: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) }); setStatus('idle'); setMessage('') }
  const completionFields = [form.full_name, form.email, form.education, form.degree, form.specialization, form.experience_level, form.career_interests.length, form.target_roles.length, form.skills.length, form.career_goals]
  const completion = Math.round(completionFields.filter((value) => Boolean(value)).length / completionFields.length * 100)
  const loading = profile === null
  const save = async () => { if (profile === null) { setStatus('error'); setMessage('Your profile is not ready yet.'); return } if (!form.full_name.trim()) { setStatus('error'); setMessage('Full name is required.'); return } if (!/^\S+@\S+\.\S+$/.test(form.email)) { setStatus('error'); setMessage('Please enter a valid email address.'); return } setSaving(true); setStatus('idle'); setMessage(''); try { const savedProfile = await updateProfile(profile.id, form); onProfileSaved(savedProfile); setStatus('success'); setMessage('Profile saved.') } catch (error: unknown) { setStatus('error'); setMessage(error instanceof Error ? error.message : 'We could not save your profile. Please try again.') } finally { setSaving(false) } }
  return <><PageHeading eyebrow="CAREER PROFILE" title="Your structured context." lede="This information is combined with extracted resume data and passed to career services." action={<button className="primary-button" disabled={loading || saving} onClick={save}>{saving ? 'Saving...' : 'Save changes'}</button>} />{loading && <div className="architecture-note" role="status">Loading your saved profile...</div>}{!loading && status === 'error' && <div className="error-notice" role="alert">{message} <button className="text-button" onClick={() => window.location.reload()}>Retry</button></div>}{!loading && status === 'success' && <div className="success-notice" role="status">{message}</div>}<section className="profile-layout"><form className="card form-card" onSubmit={(event) => { event.preventDefault(); void save() }}><div className="card-heading"><div><p className="eyebrow">CORE DETAILS</p><h3>About you</h3></div><span className="completion-label">{completion}% complete</span></div><div className="form-grid"><label>Full name<input value={form.full_name} onChange={updateText('full_name')} disabled={loading || saving} /></label><label>Email address<input type="email" value={form.email} onChange={updateText('email')} disabled={loading || saving} /></label><label>Education<input value={form.education ?? ''} onChange={updateText('education')} disabled={loading || saving} /></label><label>Degree<input value={form.degree ?? ''} onChange={updateText('degree')} disabled={loading || saving} /></label><label>Specialization<input value={form.specialization ?? ''} onChange={updateText('specialization')} disabled={loading || saving} /></label><label>Experience level<input value={form.experience_level ?? ''} onChange={updateText('experience_level')} disabled={loading || saving} /></label><label>Career interests<input value={form.career_interests.join(', ')} onChange={updateList('career_interests')} disabled={loading || saving} /></label><label>Target roles<input value={form.target_roles.join(', ')} onChange={updateList('target_roles')} disabled={loading || saving} /></label><label>Skills<input value={form.skills.join(', ')} onChange={updateList('skills')} disabled={loading || saving} /></label><label className="full-width">Career goals<textarea value={form.career_goals ?? ''} onChange={updateText('career_goals')} disabled={loading || saving} /></label></div>{status === 'error' && message && !loading && <p className="auth-error" role="alert">{message}</p>}</form><aside className="card profile-aside"><p className="eyebrow">PROFILE STATUS</p><div className="profile-score"><strong>{completion}%</strong><span>{completion === 100 ? 'ready for guidance' : 'in progress'}</span></div><div className="progress-track"><span style={{ width: `${completion}%` }} /></div><p className="muted">Your profile, resume and learning activity work together as shared context.</p><div className="aside-divider" /><p className="eyebrow">PROFILE SECTIONS</p><ul className="check-list"><li className={form.full_name && form.email ? 'done' : ''}>Personal details</li><li className={form.career_interests.length ? 'done' : ''}>Career interests</li><li className={form.education || form.degree ? 'done' : ''}>Education details</li><li className={form.skills.length ? 'done' : ''}>Skills and technologies</li><li className={form.target_roles.length || form.career_goals ? 'done' : ''}>Career direction</li></ul></aside></section></>
}
function RealResumeView({ file, lifecycle, restoring, notice, resumeRecord, onDrop, onFileChange, onAnalyze, onReprocess }: {
  file: File | null
  lifecycle: ResumeLifecycle
  restoring: boolean
  notice: string
  resumeRecord: ResumeRecord | null
  onDrop: (event: DragEvent<HTMLDivElement>) => void
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void
  onAnalyze: () => void
  onReprocess: () => void
}) {
  const busy = lifecycle === 'uploading' || lifecycle === 'processing'
  if (restoring) return <><PageHeading eyebrow="RESUME ANALYZER" title="Turn your resume into an advantage." lede="Checking for a previously processed resume..." /></>
  return <><PageHeading eyebrow="RESUME ANALYZER" title="Turn your resume into an advantage." lede="Upload, validate and extract your real resume context." action={<span className="service-badge"><span className="status-dot ready" /> Backend processing</span>} /><section className="resume-layout"><div className="card upload-card"><div className="card-heading"><div><p className="eyebrow">RESUME INPUT</p><h3>Upload your resume</h3></div><span className="file-support">PDF or DOCX</span></div><div className={`drop-zone ${file ? 'has-file' : ''}`} onDragOver={(event) => event.preventDefault()} onDrop={onDrop}><span className="upload-symbol">{file ? 'OK' : '+'}</span>{file ? <><strong>{file.name}</strong><p>{(file.size / 1024).toFixed(0)} KB ready to process</p></> : <><strong>Drop your resume here</strong><p>or choose a file from your device</p><label className="secondary-button">Browse files<input type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={onFileChange} /></label><small>PDF and DOCX files are supported.</small></>}</div>{notice && <div className="error-notice" role="alert">{notice}</div>}{file && lifecycle !== 'processed' && <button className="primary-button full-button" disabled={busy} onClick={() => void onAnalyze()}>{lifecycle === 'uploading' ? 'Uploading resume...' : lifecycle === 'processing' ? 'Processing resume...' : 'Process resume'}</button>}{!file && resumeRecord && (lifecycle === 'processed' || lifecycle === 'failed') && <button className="secondary-button full-button" disabled={busy} onClick={() => void onReprocess()}>{busy ? 'Reprocessing...' : 'Reprocess this resume'}</button>}{lifecycle === 'processed' && !file && <div className="success-notice" role="status">Resume processed and saved{resumeRecord ? ` — ${resumeRecord.original_filename}` : ''}.</div>}</div><div className="card processing-card"><div className="card-heading"><div><p className="eyebrow">PROCESSING</p><h3>Resume analysis</h3></div></div>{['Upload and validate', 'Extract text', 'Detect sections', 'Build structured resume'].map((label, index) => <ProcessingStep key={label} label={label} complete={lifecycle === 'processed'} active={(lifecycle === 'uploading' && index === 0) || (lifecycle === 'processing' && index === 3)} />)}</div></section></> }
function RealResumeResults({ structuredResume, onNavigate }: { structuredResume: StructuredResume | null; onNavigate: (view: View) => void }) {
  const data = structuredResume?.data
  const textOf = (item: Record<string, unknown>) => String(item.raw_text ?? item.title ?? '')
  const warnings = data?.parser_warnings ?? []
  return <section className="results-section"><div className="section-heading"><div><p className="eyebrow">STRUCTURED RESUME</p><h2>Resume context</h2></div><button className="text-button" onClick={() => onNavigate('resume')}>Process another -&gt;</button></div>{!data ? <div className="architecture-note">Process a resume to view persisted results.</div> : <>
    {warnings.length > 0 && <div className="architecture-note" role="status"><strong>Processed with warnings</strong><p>Some parts of this resume's structure may need review — this doesn't block using the app, but double-check the sections below against your actual resume.</p></div>}
    <div className="results-grid resume-result-grid">
      <article className="card result-card"><p className="eyebrow">EXTRACTED SKILLS</p>{data.skills.length > 0 ? <div className="chip-list">{data.skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div> : <p className="muted">No skills extracted.</p>}</article>
      <article className="card result-card"><p className="eyebrow">EDUCATION</p>{data.education.length > 0 ? data.education.map((item, index) => <p className="result-bullet" key={index}>+ {textOf(item)}</p>) : <p className="muted">No education entries extracted.</p>}</article>
      <article className="card result-card"><p className="eyebrow">EXPERIENCE AND INTERNSHIPS</p>{[...data.experience, ...data.internships].length > 0 ? [...data.experience, ...data.internships].map((item, index) => <p className="result-bullet" key={index}>+ {textOf(item)}</p>) : <p className="muted">No experience extracted.</p>}</article>
      <article className="card result-card"><p className="eyebrow">PROJECTS</p>{data.projects.length > 0 ? data.projects.map((item, index) => <p className="result-bullet" key={index}>+ {textOf(item)}</p>) : <p className="muted">No projects extracted.</p>}</article>
    </div>
    {(data.summary || data.certifications.length > 0 || data.achievements.length > 0 || data.qualifications.length > 0) && <div className="results-grid resume-result-grid">
      {data.summary && <article className="card result-card"><p className="eyebrow">SUMMARY</p><p className="muted">{data.summary}</p></article>}
      {data.certifications.length > 0 && <article className="card result-card"><p className="eyebrow">CERTIFICATIONS</p>{data.certifications.map((item, index) => <p className="result-bullet" key={index}>+ {textOf(item)}</p>)}</article>}
      {data.achievements.length > 0 && <article className="card result-card"><p className="eyebrow">ACHIEVEMENTS</p>{data.achievements.map((item, index) => <p className="result-bullet" key={index}>+ {textOf(item)}</p>)}</article>}
      {data.qualifications.length > 0 && <article className="card result-card"><p className="eyebrow">QUALIFICATIONS</p>{data.qualifications.map((item, index) => <p className="result-bullet" key={index}>+ {textOf(item)}</p>)}</article>}
    </div>}
  </>}</section>
}
function ProcessingStep({ label, complete, active }: { label: string; complete: boolean; active: boolean }) { return <div className="processing-step"><span className={`process-icon ${complete ? 'complete' : active ? 'active' : ''}`}>{complete ? 'OK' : active ? '...' : '00'}</span><strong>{label}</strong><span className="muted">{complete ? 'Done' : active ? 'Working' : 'Waiting'}</span></div> }
function SettingsView() { return <><PageHeading eyebrow="SETTINGS" title="Keep your workspace focused." lede="Manage the preferences that shape your career companion experience." /><section className="settings-list"><article className="card setting-row"><div><strong>Profile preferences</strong><p>Your saved career interests and target roles guide the recommendations shown to you.</p></div><span className="planned-tag">ACTIVE</span></article><article className="card setting-row"><div><strong>Data connection</strong><p>Resume analysis, your candidate profile, and job search and matching are backed by the AI Career Companion API. Skill gap, learning roadmap, and AI assistant features are still in development.</p></div><span className="planned-tag">ACTIVE</span></article><article className="card setting-row"><div><strong>Privacy</strong><p>Your resume file and extracted profile data are uploaded to and stored by the AI Career Companion backend for processing. They are not sent to any external AI provider or third-party service.</p></div><span className="planned-tag">ACTIVE</span></article></section></> }

export default App
