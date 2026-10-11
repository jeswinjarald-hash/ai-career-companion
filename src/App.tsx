import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, InputHTMLAttributes } from 'react'
import './App.css'
import './profile.css'
import { AuthApiError, getCurrentSession, login, logout, registerAccount, type AuthSession, type AuthUser } from './services/authService'
import { SESSION_EXPIRED_EVENT } from './config/api'
import { updateProfile, type CandidateProfile, type CandidateProfilePayload } from './services/profileService'
import { createCandidateContext, detectResumeSections, extractResumeText, getResumeExtraction, getStructuredResume, listProfileResumes, structureResume, uploadResume, type ResumeRecord, type StructuredResume } from './services/resumeService'
import { getJobDetails } from './services/jobService'
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
import {
  createConversation, deleteConversation, getConversation, listConversations, sendMessage,
  type ActionType, type ConversationDetail, type ConversationSummary, type MessageOut, type SuggestedAction,
} from './services/assistantService'
import { EmptyState, LongTaskStatus, PageHeading, Stat } from './components/common'
import { ApplicationTrackerView } from './components/applications/ApplicationTrackerView'
import { ApplicationDetailView } from './components/applications/ApplicationDetailView'
import { TrackerLinkPanel } from './components/applications/ApplicationWidgets'
import { formatDateTime } from './components/applications/applicationFormat'
import { profileCompletion } from './lib/profileCompletion'
import { errorText } from './lib/errorText'
import { CareersView } from './views/CareersView'
import { JobDetailsView } from './views/JobDetailsView'
import { RoadmapView } from './views/RoadmapView'
import { DashboardView } from './views/DashboardView'
import { NavDrawer, NavList } from './components/AppNav'
import { Icon } from './components/icons'
import { lifecycleForUnstructured, readinessRows, resumeCoverage, type ResumeLifecycle } from './lib/insights'
import { gapSkillsFromAnalysis, graphSkills } from './lib/skillGraphData'
import { sceneModeForView } from './lib/skillGraphScene'
import { publishScene, publishSkills } from './components/backgroundRuntime'
import { MeterChart, ScoreRing } from './components/charts'
import './components/applications/applications.css'
import './theme.css'
import { AUTH_PATHS, pathForView, routeFromLocation, viewFromLocation, viewLabel, type View } from './routing'

// The real backend calls made while processing a resume, in order. The UI only marks
// a step done after that request has returned successfully.
type ResumeStage = 'upload' | 'extract' | 'sections' | 'structure' | 'context'
const RESUME_STAGES: { id: ResumeStage; label: string }[] = [
  { id: 'upload', label: 'Upload and validate' }, { id: 'extract', label: 'Extract text' }, { id: 'sections', label: 'Detect sections' },
  { id: 'structure', label: 'Build structured resume' }, { id: 'context', label: 'Update career context' },
]
// Mirrors backend/app/services/resume_validation.py (SUPPORTED_EXTENSIONS, MAX_RESUME_SIZE);
// the backend still validates every upload — this only gives faster, clearer feedback.
const MAX_RESUME_BYTES = 10 * 1024 * 1024
const ACTION_VIEW: Partial<Record<ActionType, View>> = {
  upload_resume: 'resume', process_resume: 'resume', view_resume: 'resume-results',
  view_recommendations: 'careers', compare_jobs: 'careers', analyze_skill_gap: 'skills',
  customize_application: 'customize', prepare_interview: 'interview-prep', view_learning_plan: 'roadmap',
}

type AuthStatus = 'checking' | 'unreachable' | 'authenticated' | 'unauthenticated'

function BrandMark({ className }: { className: string }) { return <div className={className}><span aria-hidden="true">AC</span><div><strong>AI Career</strong><small>Companion</small></div></div> }

const initials = (fullName: string) => fullName.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? '').join('') || '?'

function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>('checking')
  const [authRoute, setAuthRoute] = useState(window.location.pathname)
  const [authNotice, setAuthNotice] = useState('')
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [activeProfile, setActiveProfile] = useState<CandidateProfile | null>(null)
  const [view, setView] = useState<View>(viewFromLocation)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(() => routeFromLocation().jobId)
  const [selectedApplicationId, setSelectedApplicationId] = useState<number | null>(() => routeFromLocation().applicationId)
  const [resumeFile, setResumeFile] = useState<File | null>(null)
  const [resumeLifecycle, setResumeLifecycle] = useState<ResumeLifecycle>('no_resume')
  const [resumeStage, setResumeStage] = useState<ResumeStage | null>(null)
  const [resumeRestoring, setResumeRestoring] = useState(true)
  const [resumeRecord, setResumeRecord] = useState<ResumeRecord | null>(null)
  const [structuredResume, setStructuredResume] = useState<StructuredResume | null>(null)
  const [notice, setNotice] = useState('')
  const [fileNotice, setFileNotice] = useState('')
  const [restoreError, setRestoreError] = useState('')
  const [restoreKey, setRestoreKey] = useState(0)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const restoreAttempted = useRef(false)
  const resumeBusy = useRef(false)
  const viewChanged = useRef(false)
  const authStatusRef = useRef(authStatus)
  useEffect(() => { authStatusRef.current = authStatus }, [authStatus])

  const checkSession = () => {
    setAuthStatus('checking')
    return getCurrentSession().then((session) => {
      if (session) {
        setCurrentUser(session.user)
        setActiveProfile(session.profile)
        setAuthStatus('authenticated')
      } else {
        setAuthStatus('unauthenticated')
      }
    }).catch((error: unknown) => {
      // Status 0 = the API could not be reached at all; anything else is a real auth answer.
      setAuthStatus(error instanceof AuthApiError && error.status === 0 ? 'unreachable' : 'unauthenticated')
    })
  }
  useEffect(() => { void checkSession() }, [])
  useEffect(() => { const onPopState = () => { const route = routeFromLocation(); setView(route.view); setSelectedApplicationId(route.applicationId); if (route.jobId) setSelectedJobId(route.jobId); setAuthRoute(window.location.pathname) }; window.addEventListener('popstate', onPopState); return () => window.removeEventListener('popstate', onPopState) }, [])
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
      // No structured result: either the last attempt failed, or processing never finished
      // (the stored file can then simply be analysed now — it is not a failure).
      const lifecycle = lifecycleForUnstructured(latest)
      if (lifecycle === 'failed') {
        const extraction = await getResumeExtraction(latest.id).catch(() => null)
        setNotice(extraction?.error_message || 'Resume text extraction failed. Please upload a different file.')
      }
      setResumeLifecycle(lifecycle)
    }).catch((error: unknown) => {
      // Loading the status failed — not the analysis. Shown as a retryable load error.
      setRestoreError(errorText(error, 'We could not load your saved resume.'))
    }).finally(() => setResumeRestoring(false))
  }, [authStatus, activeProfile, restoreKey])
  const retryRestore = () => { restoreAttempted.current = false; setRestoreError(''); setResumeRestoring(true); setRestoreKey((key) => key + 1) }

  // Real skills for the decorative skill graph: the analysed active resume's extracted skills
  // and the user's own profile skills — already in memory, no extra request. Cleared when
  // signed out, while a replacement resume is being processed, or when nothing is analysed.
  useEffect(() => {
    const signedIn = authStatus === 'authenticated'
    publishSkills(graphSkills({
      resumeSkills: signedIn && resumeLifecycle === 'processed' ? structuredResume?.data.skills : null,
      profileSkills: signedIn ? activeProfile?.skills : null,
    }))
  }, [authStatus, resumeLifecycle, structuredResume, activeProfile])
  // Route scene for the skill graph: the current screen's visual mode, and whether a resume
  // upload/analysis request is really in flight. Signed-out screens use the neutral default.
  useEffect(() => {
    const signedIn = authStatus === 'authenticated'
    publishScene({ mode: sceneModeForView(signedIn ? view : null), resumeProcessing: signedIn && (resumeLifecycle === 'uploading' || resumeLifecycle === 'processing') })
  }, [authStatus, view, resumeLifecycle])

  const label = authStatus === 'authenticated' ? viewLabel(view) : authStatus === 'checking' ? 'Loading' : authStatus === 'unreachable' ? 'Connection problem' : authRoute === '/signup' ? 'Create account' : 'Sign in'
  useEffect(() => { document.title = `${label} · AI Career Companion` }, [label])
  // Moves focus to the new page's heading after in-app navigation, so keyboard and
  // screen-reader users land at the start of the new content (not on first load).
  useEffect(() => {
    if (!viewChanged.current) { viewChanged.current = true; return }
    window.scrollTo(0, 0)
    const heading = document.querySelector<HTMLElement>('#main-content h1')
    if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }) }
  }, [view])

  const go = (next: View, jobId: string | null = selectedJobId) => { setView(next); setNotice(''); window.history.pushState({}, '', pathForView(next, jobId, selectedApplicationId)) }
  // Sets the URL directly with the just-selected job id rather than going through
  // go('job-details'), which would otherwise read selectedJobId from this render's
  // closure before the setSelectedJobId update above has been applied.
  const openJobDetails = (jobId: string) => { setSelectedJobId(jobId); setView('job-details'); setNotice(''); window.history.pushState({}, '', `/jobs/${jobId}`) }
  const openApplication = (applicationId: number) => { setSelectedApplicationId(applicationId); setView('application-details'); setNotice(''); window.history.pushState({}, '', `/applications/${applicationId}`) }
  // Opens an existing generated-materials workspace for a tracked dataset opportunity.
  const openJobWorkspace = (jobId: string, next: 'customize' | 'interview-prep') => { setSelectedJobId(jobId); go(next, jobId) }
  const handleAssistantAction = (action: SuggestedAction) => {
    if (action.action === 'view_job' && action.job_id) { openJobDetails(action.job_id); return }
    if (action.job_id) setSelectedJobId(action.job_id)
    const nextView = ACTION_VIEW[action.action]
    if (nextView) go(nextView, action.job_id ?? selectedJobId)
  }
  // Selecting a file only stages it: the currently active, processed resume stays in
  // place everywhere until the new upload has actually been accepted by the backend.
  const chooseFile = (file: File | undefined) => {
    if (!file || resumeBusy.current) return
    const extension = file.name.toLowerCase().split('.').pop()
    if (!['pdf', 'docx'].includes(extension ?? '')) { setFileNotice('That file type is not supported. Please choose a PDF or DOCX resume.'); return }
    if (file.size === 0) { setFileNotice('That file is empty. Please choose a different resume file.'); return }
    if (file.size > MAX_RESUME_BYTES) { setFileNotice(`That file is ${(file.size / 1024 / 1024).toFixed(1)} MB. Resumes must be 10 MB or smaller.`); return }
    setResumeFile(file); setFileNotice('')
  }
  // Runs extraction → section detection → structuring → candidate context for a stored
  // resume. Each backend step is an upsert keyed by resume id, so reruns never duplicate state.
  const processStoredResume = async (resumeId: number) => {
    setResumeLifecycle('processing')
    setResumeStage('extract'); await extractResumeText(resumeId)
    setResumeStage('sections'); await detectResumeSections(resumeId)
    setResumeStage('structure'); const structured = await structureResume(resumeId)
    setStructuredResume(structured)
    if (activeProfile) { setResumeStage('context'); await createCandidateContext(activeProfile.id, resumeId) }
    setResumeStage(null)
    setResumeLifecycle('processed')
  }
  const analyze = async () => {
    if (!resumeFile || resumeBusy.current) return
    if (activeProfile === null) { setNotice('Your career profile is not ready yet. Please refresh and try again.'); return }
    resumeBusy.current = true
    const previousLifecycle = resumeLifecycle
    let uploaded: ResumeRecord | null = null
    setResumeLifecycle('uploading'); setResumeStage('upload'); setNotice(''); setFileNotice('')
    try {
      uploaded = await uploadResume(activeProfile.id, resumeFile)
      // From here the new upload is the active resume; results from the previous one
      // must not be shown as if they belonged to it.
      setResumeRecord(uploaded)
      setStructuredResume(null)
      // The accepted file is now the stored resume: un-stage it, so a failure below offers
      // "Retry analysis" on the stored copy instead of asking for the upload again.
      setResumeFile(null)
      await processStoredResume(uploaded.id)
      go('resume-results')
    } catch (error: unknown) {
      // A rejected upload (e.g. invalid file) leaves the previously active resume in
      // place; a failure after the upload was accepted marks the new resume as failed.
      if (uploaded === null) { setResumeLifecycle(previousLifecycle); setResumeStage(null) } else setResumeLifecycle('failed')
      setNotice(errorText(error, 'We could not process this resume.'))
    } finally {
      resumeBusy.current = false
    }
  }
  const reprocessResume = async () => {
    if (!resumeRecord || resumeBusy.current) return
    resumeBusy.current = true
    setNotice('')
    try {
      await processStoredResume(resumeRecord.id)
    } catch (error: unknown) {
      setResumeLifecycle('failed')
      setNotice(errorText(error, 'We could not reprocess this resume.'))
    } finally {
      resumeBusy.current = false
    }
  }
  const resetWorkspace = () => {
    setCurrentUser(null)
    setActiveProfile(null)
    setStructuredResume(null)
    setResumeFile(null)
    setResumeRecord(null)
    setResumeLifecycle('no_resume')
    setResumeStage(null)
    setResumeRestoring(true)
    setSelectedJobId(null)
    setSelectedApplicationId(null)
    setNotice(''); setFileNotice(''); setRestoreError('')
    restoreAttempted.current = false
  }
  const navigateAuth = (path: string) => { window.history.pushState({}, '', path); setAuthRoute(path) }
  const handleAuthenticated = (session: AuthSession) => {
    // A deep link opened while signed out (e.g. /jobs/JOB-0001) is kept; the sign-in
    // and sign-up pages themselves continue to the dashboard. The job/application
    // selection is re-read from the URL too: after a session expiry resetWorkspace()
    // cleared it, and the view alone would reopen with nothing selected. The backend
    // still checks ownership when the selected resource is loaded.
    if (AUTH_PATHS.includes(window.location.pathname)) { window.history.replaceState({}, '', '/dashboard'); setView('dashboard') } else {
      const route = routeFromLocation()
      setView(route.view); setSelectedJobId(route.jobId); setSelectedApplicationId(route.applicationId)
    }
    setAuthNotice('')
    setCurrentUser(session.user); setActiveProfile(session.profile); setAuthStatus('authenticated')
  }
  const handleLogout = async () => {
    try { await logout() } catch { /* the session is cleared locally either way */ } finally {
      resetWorkspace()
      setAuthStatus('unauthenticated')
      navigateAuth('/')
    }
  }
  // Any authenticated request answering 401 means the session is gone: clear every
  // piece of account data from memory and return to sign-in with an explanation.
  useEffect(() => {
    const onExpired = () => {
      if (authStatusRef.current !== 'authenticated') return
      resetWorkspace()
      setAuthNotice('Your session has expired. Please sign in again.')
      setAuthStatus('unauthenticated')
      setAuthRoute(window.location.pathname)
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  }, [])
  const activeResumeId = resumeLifecycle === 'processed' ? resumeRecord?.id ?? null : null
  const content = view === 'profile' ? <ProfileView profile={activeProfile} onProfileSaved={setActiveProfile} /> : view === 'resume' ? <RealResumeView file={resumeFile} lifecycle={resumeLifecycle} stage={resumeStage} restoring={resumeRestoring} notice={notice} fileNotice={fileNotice} resumeRecord={resumeRecord} onFileSelected={chooseFile} onClearFile={() => { setResumeFile(null); setFileNotice('') }} onAnalyze={analyze} onReprocess={reprocessResume} onViewResults={() => go('resume-results')} /> : view === 'resume-results' ? <RealResumeResults structuredResume={structuredResume} lifecycle={resumeLifecycle} resumeRecord={resumeRecord} onNavigate={go} onReprocess={reprocessResume} /> : view === 'careers' ? <CareersView resumeId={activeResumeId} onOpenJob={openJobDetails} onUploadResume={() => go('resume')} /> : view === 'job-details' ? <JobDetailsView jobId={selectedJobId} resumeId={activeResumeId} onBack={() => go('careers')} onAnalyzeSkillGap={() => go('skills')} onCustomizeApplication={() => go('customize')} onInterviewPrep={() => go('interview-prep')} onOpenApplication={openApplication} /> : view === 'skills' ? <SkillsView resumeId={activeResumeId} jobId={selectedJobId} onRoadmap={() => go('roadmap')} onSearchJobs={() => go('careers')} onUploadResume={() => go('resume')} onCustomizeApplication={() => go('customize')} onInterviewPrep={() => go('interview-prep')} /> : view === 'customize' ? <CustomizeView resumeId={activeResumeId} jobId={selectedJobId} structuredResume={structuredResume} onSearchJobs={() => go('careers')} onUploadResume={() => go('resume')} onInterviewPrep={() => go('interview-prep')} onOpenApplication={openApplication} /> : view === 'interview-prep' ? <InterviewPrepView resumeId={activeResumeId} jobId={selectedJobId} structuredResume={structuredResume} onSearchJobs={() => go('careers')} onUploadResume={() => go('resume')} onOpenApplication={openApplication} /> : view === 'applications' ? <ApplicationTrackerView onOpenApplication={openApplication} onBrowseOpportunities={() => go('careers')} /> : view === 'application-details' ? <ApplicationDetailView applicationId={selectedApplicationId} resumeId={activeResumeId} onBack={() => go('applications')} onOpenCustomization={(jobId) => openJobWorkspace(jobId, 'customize')} onOpenInterviewPrep={(jobId) => openJobWorkspace(jobId, 'interview-prep')} onOpenJob={openJobDetails} /> : view === 'roadmap' ? <RoadmapView resumeId={activeResumeId} /> : view === 'assistant' ? <AssistantView resumeId={activeResumeId} jobId={selectedJobId} onAction={handleAssistantAction} /> : view === 'progress' ? <ProgressView profile={activeProfile} resumeLifecycle={resumeLifecycle} structuredResume={structuredResume} /> : view === 'settings' ? <SettingsView /> : <DashboardView currentUser={currentUser} profile={activeProfile} resumeLifecycle={resumeLifecycle} resumeRestoring={resumeRestoring} resumeRecord={resumeRecord} structuredResume={structuredResume} processingLabel={RESUME_STAGES.find((item) => item.id === resumeStage)?.label ?? null} notice={notice} loadError={restoreError} onRetryLoad={retryRestore} onNavigate={go} onOpenApplication={openApplication} onOpenJob={openJobDetails} onReprocess={() => void reprocessResume()} />
  if (authStatus === 'checking') return <main className="auth-page single"><section className="auth-panel"><BrandMark className="auth-brand" /><p className="muted" role="status">Loading your workspace...</p></section></main>
  if (authStatus === 'unreachable') return <main className="auth-page single"><section className="auth-panel"><BrandMark className="auth-brand" /><div className="auth-copy"><p className="eyebrow">CONNECTION PROBLEM</p><h1>We can't reach the server.</h1><p>The AI Career Companion API is not responding. Check that the backend is running and that you are online, then try again.</p></div><div className="error-notice auth-status-notice" role="alert">Could not connect to the API.</div><button className="primary-button auth-submit" onClick={() => void checkSession()}>Try again</button></section></main>
  if (authStatus === 'unauthenticated') { if (authRoute === '/signup') return <SignupView onAuthenticated={handleAuthenticated} onSwitch={() => navigateAuth('/')} />; if (authRoute === '/onboarding') return <OnboardingView onSignup={() => navigateAuth('/signup')} />; return <LoginView notice={authNotice} onAuthenticated={handleAuthenticated} onSwitch={() => navigateAuth('/signup')} /> }
  const navigate = (next: View) => { setMenuOpen(false); go(next) }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <aside className="sidebar" aria-label="Sidebar">
      <BrandMark className="brand-mark" />
      <NavList view={view} onNavigate={navigate} label="Primary navigation" />
    </aside>
    <div className="main-content">
      <header className="topbar">
        <button ref={menuButtonRef} className="menu-button" aria-label="Open navigation menu" aria-expanded={menuOpen} aria-haspopup="dialog" onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
        <div className="breadcrumbs"><span>Workspace</span><span aria-hidden="true">/</span><strong>{label}</strong></div>
        <div className="account"><div className="avatar" aria-hidden="true">{initials(currentUser?.full_name ?? '')}</div><div className="account-text"><strong>{currentUser?.full_name}</strong><small>{currentUser?.email}</small></div><button className="text-button" onClick={() => void handleLogout()}>Sign out</button></div>
      </header>
      <NavDrawer open={menuOpen} onClose={() => setMenuOpen(false)} returnFocusTo={menuButtonRef}>
        <NavList view={view} onNavigate={navigate} label="Mobile navigation" />
      </NavDrawer>
      <main className="page-wrap" id="main-content"><div key={view} className="page-enter">{content}</div></main>
    </div>
  </div>
}


type FieldError = { field: string; message: string } | null
// Associates a validation message with its input (aria-invalid + aria-describedby) so
// screen readers announce which field needs attention, not just that something failed.
function AuthField({ id, label, error, ...input }: { id: string; label: string; error: FieldError } & InputHTMLAttributes<HTMLInputElement>) {
  const invalid = error?.field === id
  return <label htmlFor={id}>{label}<input id={id} aria-invalid={invalid || undefined} aria-describedby={invalid ? 'auth-error' : undefined} {...input} /></label>
}

function AuthAside({ eyebrow, title, steps }: { eyebrow: string; title: string; steps: [string, string][] }) {
  return <aside className="auth-aside"><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><ol className="auth-flow-list">{steps.map(([heading, detail], index) => <li className="auth-flow" key={heading}><span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span><div><strong>{heading}</strong><small>{detail}</small></div></li>)}</ol></aside>
}

function LoginView({ notice, onAuthenticated, onSwitch }: { notice: string; onAuthenticated: (session: AuthSession) => void; onSwitch: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<FieldError>(null)
  const [submitting, setSubmitting] = useState(false)
  const submit = async () => {
    if (submitting) return
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) { setError({ field: 'login-email', message: 'Enter a valid email address.' }); return }
    if (!password) { setError({ field: 'login-password', message: 'Enter your password.' }); return }
    setError(null)
    setSubmitting(true)
    try {
      const session = await login({ email: email.trim(), password })
      onAuthenticated(session)
    } catch (err: unknown) {
      setError({ field: '', message: errorText(err, 'We could not sign you in. Please try again.') })
    } finally {
      setSubmitting(false)
    }
  }
  return <main className="auth-page"><section className="auth-panel"><BrandMark className="auth-brand" /><div className="auth-copy"><p className="eyebrow">STUDENT WORKSPACE</p><h1>Your career context, in one place.</h1><p>Sign in to manage your candidate profile and continue building your career direction.</p></div>
    {notice && <div className="architecture-note auth-status-notice" role="status">{notice}</div>}
    <form className="auth-form" noValidate onSubmit={(event) => { event.preventDefault(); void submit() }}>
      <AuthField id="login-email" label="Email address" error={error} type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" disabled={submitting} />
      <AuthField id="login-password" label="Password" error={error} type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" disabled={submitting} />
      {error && <p className="auth-error" id="auth-error" role="alert">{error.message}</p>}
      <button className="primary-button auth-submit" disabled={submitting}>{submitting ? 'Signing in...' : 'Sign in'}</button>
    </form>
    <p className="auth-switch">New here? <button className="text-button" onClick={onSwitch}>Create an account</button></p></section>
    <AuthAside eyebrow="AI CAREER COMPANION" title="Start with a clearer picture of where you are." steps={[['Understand your profile', 'Bring your career context together'], ['Find your direction', 'Explore opportunities and skill gaps'], ['Keep moving forward', 'Tailor applications and prepare for interviews']]} /></main>
}

function SignupView({ onAuthenticated, onSwitch }: { onAuthenticated: (session: AuthSession) => void; onSwitch: () => void }) {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<FieldError>(null)
  const [submitting, setSubmitting] = useState(false)
  const submit = async () => {
    if (submitting) return
    if (!fullName.trim()) { setError({ field: 'signup-name', message: 'Enter your full name.' }); return }
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) { setError({ field: 'signup-email', message: 'Enter a valid email address.' }); return }
    if (password.length < 8) { setError({ field: 'signup-password', message: 'Password must contain at least 8 characters.' }); return }
    if (password !== confirmPassword) { setError({ field: 'signup-confirm', message: 'Passwords do not match.' }); return }
    setError(null)
    setSubmitting(true)
    try {
      const session = await registerAccount({ full_name: fullName.trim(), email: email.trim(), password, confirm_password: confirmPassword })
      onAuthenticated(session)
    } catch (err: unknown) {
      setError({ field: '', message: errorText(err, 'We could not create your account. Please try again.') })
    } finally {
      setSubmitting(false)
    }
  }
  return <main className="auth-page"><section className="auth-panel"><BrandMark className="auth-brand" /><div className="auth-copy"><p className="eyebrow">CREATE YOUR WORKSPACE</p><h1>Start with your career context.</h1><p>Create an account, then complete your career profile.</p></div>
    <form className="auth-form" noValidate onSubmit={(event) => { event.preventDefault(); void submit() }}>
      <AuthField id="signup-name" label="Full name" error={error} autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Your name" disabled={submitting} />
      <AuthField id="signup-email" label="Email address" error={error} type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" disabled={submitting} />
      <AuthField id="signup-password" label="Password" error={error} type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" disabled={submitting} />
      <AuthField id="signup-confirm" label="Confirm password" error={error} type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Re-enter your password" disabled={submitting} />
      {error && <p className="auth-error" id="auth-error" role="alert">{error.message}</p>}
      <button className="primary-button auth-submit" disabled={submitting}>{submitting ? 'Creating account...' : 'Create account'}</button>
    </form>
    <p className="auth-switch">Already have an account? <button className="text-button" onClick={onSwitch}>Sign in</button></p></section>
    <AuthAside eyebrow="YOUR FIRST STEPS" title="Build a profile that can grow with you." steps={[['Tell us about your direction', 'Interests and experience'], ['Add your resume', 'Skills and projects extracted']]} /></main>
}
function OnboardingView({ onSignup }: { onSignup: () => void }) { return <main className="auth-page"><section className="auth-panel"><BrandMark className="auth-brand" /><div className="auth-copy"><p className="eyebrow">CREATE YOUR ACCOUNT</p><h1>Let's get your workspace set up.</h1><p>Create an account to build your career profile and upload your resume.</p></div><button className="primary-button auth-submit" onClick={onSignup}>Go to sign up</button></section><AuthAside eyebrow="A CLEAR START" title="Your profile becomes the context behind every next step." steps={[['Profile', 'Personal and career details'], ['Guidance', 'Recommendations shaped around you']]} /></main> }
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
function SkillsView({ resumeId, jobId, onRoadmap, onSearchJobs, onUploadResume, onCustomizeApplication, onInterviewPrep }: { resumeId: number | null; jobId: string | null; onRoadmap: () => void; onSearchJobs: () => void; onUploadResume: () => void; onCustomizeApplication: () => void; onInterviewPrep: () => void }) {
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

  // Real gaps from this analysis accent the skill graph; cleared when the analysis is reset
  // (new resume/job) or this screen unmounts (navigation, sign-out).
  useEffect(() => {
    publishScene({ gapSkills: gapSkillsFromAnalysis(analysis) })
    return () => publishScene({ gapSkills: [] })
  }, [analysis])

  return <>
    <PageHeading eyebrow="Skill Gaps" title="Understand what to learn next." lede="A grounded comparison of your resume against the opportunity you selected." action={<button className="primary-button" onClick={onSearchJobs}>Search opportunities →</button>} />
    {resumeId === null && <EmptyState message="Upload and process your resume before running skill gap analysis." action={<button className="secondary-button" onClick={onUploadResume}>Go to Resume Studio</button>} />}
    {resumeId !== null && jobId === null && <EmptyState message={'Select an opportunity to analyze your skill gaps. Open its details and choose "Analyze Skill Gaps".'} />}
    {resumeId !== null && jobId !== null && status === 'loading' && <p className="muted" role="status">{analysis ? 'Refreshing your analysis...' : 'Analyzing your skill gaps against this opportunity...'}</p>}
    {resumeId !== null && jobId !== null && status === 'error' && <div className="error-notice" role="alert">{error} <button className="text-button" onClick={() => runAnalysis(resumeId, jobId)}>Retry</button></div>}
    {analysis && <>
      <section className="card comparison-card">
        <div className="card-heading">
          <div><p className="eyebrow">SELECTED OPPORTUNITY</p><h3>{analysis.job_title}</h3></div>
          <button className="text-button" onClick={() => resumeId !== null && jobId !== null && runAnalysis(resumeId, jobId)} disabled={status === 'loading'}>Refresh analysis →</button>
        </div>
        <p className="muted">{analysis.company} · {analysis.domain} · {analysis.location}</p>
        {analysis.stale && <p className="result-bullet">Your profile has changed since this analysis was generated. Refresh for updated results.</p>}
      </section>
      <div className="skill-summary-grid">
        <div className="card skill-score-card">
          <p className="eyebrow">SKILL READINESS</p>
          <div className="ring-row"><ScoreRing value={analysis.summary.overall_readiness} label="Skill readiness" caption="ready" /><div>
          <p className="muted">Required skills matched: {analysis.summary.required_requirements_met}/{analysis.summary.required_requirements_total} &middot; Preferred: {analysis.summary.preferred_requirements_met}/{analysis.summary.preferred_requirements_total}</p>
          </div></div>
          <p className="muted">Weighted share of this role’s requirements your resume and profile demonstrate, over the components that could be assessed. Separate from the match score in Opportunities.</p>
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
        <MeterChart title="How readiness is calculated"
          description={<>Each component’s score (requirements met, with partial credit for related evidence) and its weight. Readiness is the weighted average of the assessed components{analysis.summary.score_breakdown.some((component) => !component.included) ? '; components marked “Not available” could not be assessed and are left out of the average' : ''}.</>}
          labelHeader="Component" valueHeader="Score" detailHeader="Weight · evidence" max={100} emptyText="No score breakdown was returned for this analysis."
          rows={readinessRows(analysis.summary.score_breakdown).map((row) => ({ key: row.key, label: row.label, value: row.percent, display: row.percent === null ? '—' : `${row.percent}%`, detail: `${row.weightPercent}% weight · ${row.detail}` }))} />
      </section>
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
      <div className="detail-actions"><button className="primary-button" onClick={onCustomizeApplication}>Customize Application →</button><button className="secondary-button" onClick={onInterviewPrep}>Prepare for Interview →</button><button className="secondary-button" onClick={onRoadmap}>View learning roadmap</button></div>
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
    <label className="muted bullet-label"><strong>Tailored{edited ? ' (edited)' : ''}:</strong>
      <textarea className="cover-letter-editor bullet-editor" value={draft} onChange={(event) => onEdit(sourcePath, event.target.value)} rows={2} />
    </label>
    {jobKeywordsUsed.length > 0 && <div className="tag-row">{jobKeywordsUsed.map((keyword) => <span key={keyword}>{keyword}</span>)}</div>}
    <ProvenanceDetails evidenceIds={evidenceIds} evidenceById={evidenceById} />
  </div>
}

const GENERATION_LABEL: Record<GenerationMode, string> = { llm: 'AI Enhanced', deterministic_fallback: 'Grounded Fallback' }
const GENERATION_TONE: Record<GenerationMode, string> = { llm: 'strong', deterministic_fallback: 'adequate' }

function CustomizeView({ resumeId, jobId, structuredResume, onSearchJobs, onUploadResume, onInterviewPrep, onOpenApplication }: {
  resumeId: number | null
  jobId: string | null
  structuredResume: StructuredResume | null
  onSearchJobs: () => void
  onUploadResume: () => void
  onInterviewPrep: () => void
  onOpenApplication: (applicationId: number) => void
}) {
  const [customization, setCustomization] = useState<ApplicationCustomization | null>(null)
  const [versions, setVersions] = useState<ApplicationCustomizationSummary[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [error, setError] = useState('')
  const [summaryDraft, setSummaryDraft] = useState('')
  const [coverLetterDraft, setCoverLetterDraft] = useState('')
  const [bulletDrafts, setBulletDrafts] = useState<Record<string, string>>({})
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [saveError, setSaveError] = useState('')
  const [exportError, setExportError] = useState('')
  const [exporting, setExporting] = useState('')

  const applyResult = (result: ApplicationCustomization) => {
    setCustomization(result)
    setSummaryDraft(result.tailored_resume.summary)
    setCoverLetterDraft(result.cover_letter_text)
    setBulletDrafts(bulletDraftsFrom(result.tailored_resume))
    setSaveStatus('idle'); setSaveError('')
  }
  const hasUnsavedEdits = customization !== null && (summaryDraft !== customization.tailored_resume.summary || coverLetterDraft !== customization.cover_letter_text
    || Object.entries(bulletDraftsFrom(customization.tailored_resume)).some(([sourcePath, text]) => (bulletDrafts[sourcePath] ?? text) !== text))
  const markEdited = () => { setSaveStatus('idle'); setSaveError('') }

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
    if (resumeId === null || jobId === null || status === 'loading') return
    setStatus('loading'); setError('')
    try {
      const result = await generateCustomization(resumeId, jobId)
      applyResult(result)
      setVersions(await listCustomizations(resumeId, jobId))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not generate application materials for this resume and opportunity.')
      // A timed-out or dropped request may still have completed on the server.
      void listCustomizations(resumeId, jobId).then(setVersions).catch(() => undefined)
    }
  }

  const regenerate = async () => {
    if (resumeId === null || customization === null || status === 'loading') return
    if (hasUnsavedEdits && !window.confirm('Regenerating creates a new version and your unsaved edits will not be included. Continue?')) return
    setStatus('loading'); setError('')
    try {
      const result = await regenerateCustomization(resumeId, customization.id)
      applyResult(result)
      setVersions(await listCustomizations(resumeId, customization.job_id))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not regenerate application materials.')
      void listCustomizations(resumeId, customization.job_id).then(setVersions).catch(() => undefined)
    }
  }

  const selectVersion = async (id: number) => {
    if (resumeId === null || id === customization?.id) return
    if (hasUnsavedEdits && !window.confirm('You have unsaved edits. Switch versions and discard them?')) return
    setError('')
    try {
      const full = await getCustomization(resumeId, id)
      if (full) applyResult(full)
    } catch (err: unknown) {
      setStatus('error'); setError(errorText(err, 'We could not load that version.'))
    }
  }

  const editBullet = (sourcePath: string, value: string) => { setBulletDrafts((drafts) => ({ ...drafts, [sourcePath]: value })); markEdited() }

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
    setSaveStatus('saving'); setSaveError('')
    try {
      const updated = await updateCustomization(resumeId, customization.id, payload)
      applyResult(updated)
      setSaveStatus('saved')
    } catch (err: unknown) {
      // Previously this error was stored but never rendered, so a failed save looked like nothing happened.
      setSaveStatus('idle')
      setSaveError(errorText(err, 'We could not save your edits.'))
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

  if (resumeId === null) return <><PageHeading eyebrow="Application materials" title="Tailor your resume and cover letter." lede="Generate a resume and cover letter tailored to one opportunity, grounded in your own resume." /><EmptyState message="Upload and process your resume before customizing an application." action={<button className="secondary-button" onClick={onUploadResume}>Go to Resume Studio</button>} /></>
  if (jobId === null) return <><PageHeading eyebrow="Application materials" title="Tailor your resume and cover letter." lede="Select an opportunity to customize your application." action={<button className="primary-button" onClick={onSearchJobs}>Search opportunities →</button>} /><EmptyState message={<>Open an opportunity's details or your skill gap analysis and choose “Customize Application” to get started.</>} /></>

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
        ? <button className="secondary-button" onClick={() => void regenerate()} disabled={status === 'loading'}>{status === 'loading' ? 'Regenerating...' : 'Regenerate →'}</button>
        : <button className="primary-button" onClick={() => void generate()} disabled={status === 'loading'}>{status === 'loading' ? 'Generating...' : 'Generate tailored application →'}</button>}
    />
    {status === 'loading' && <LongTaskStatus label={customization ? 'Regenerating your tailored application…' : 'Generating your tailored application…'} detail="Matching your resume evidence to this role and validating every claim. With an AI provider configured this can take up to a couple of minutes; results appear only after the server confirms them." />}
    {status === 'error' && <div className="error-notice" role="alert">{error}</div>}

    {versions.length > 1 && <div className="tag-row">{versions.map((item) => <span key={item.id}><button className={`text-button ${customization?.id === item.id ? 'active' : ''}`} onClick={() => void selectVersion(item.id)}>v{item.version} · {GENERATION_LABEL[item.generation_mode]}{item.stale ? ' (stale)' : ''}</button></span>)}</div>}

    {customization && <>
      <TrackerLinkPanel kind="customization" jobId={customization.job_id} artifactId={customization.id} onOpenApplication={onOpenApplication} />
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
        ? <div className="success-notice" role="status">Grounding check passed — the generated text names no skill, technology, qualification, employer, achievement or metric that is missing from your resume/profile.</div>
        : <div className="error-notice" role="alert"><strong>{customization.validation.removed_claims.length > 0 ? 'Grounding warnings found — unsupported claims were removed.' : 'Grounding could not be confirmed.'}</strong><ul>{customization.validation.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}

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
        <textarea className="cover-letter-editor" aria-label="Tailored professional summary" value={summaryDraft} onChange={(event) => { setSummaryDraft(event.target.value); markEdited() }} rows={3} />
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
        <textarea className="cover-letter-editor" aria-label="Tailored cover letter" value={coverLetterDraft} onChange={(event) => { setCoverLetterDraft(event.target.value); markEdited() }} rows={10} />
        {customization.user_edits.edited_fields.includes('cover_letter_text') && <p className="muted">User edited — no longer treated as an AI-generated, evidence-verified claim.</p>}
        <ProvenanceDetails evidenceIds={[...new Set(customization.cover_letter.flatMap((s) => s.evidence_ids))]} evidenceById={evidenceById} />
      </section>

      <div className="detail-actions">
        <button className="primary-button" onClick={() => void saveEdits()} disabled={saveStatus === 'saving'}>{saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved ✓' : 'Save edits'}</button>
        <button className="secondary-button" onClick={() => void download('resume', 'pdf')} disabled={exporting !== ''}>{exporting === 'resume-pdf' ? 'Exporting...' : 'Export resume (PDF)'}</button>
        <button className="secondary-button" onClick={() => void download('resume', 'docx')} disabled={exporting !== ''}>{exporting === 'resume-docx' ? 'Exporting...' : 'Export resume (DOCX)'}</button>
        <button className="secondary-button" onClick={() => void download('cover_letter', 'pdf')} disabled={exporting !== ''}>{exporting === 'cover_letter-pdf' ? 'Exporting...' : 'Export cover letter (PDF)'}</button>
        <button className="secondary-button" onClick={() => void download('cover_letter', 'docx')} disabled={exporting !== ''}>{exporting === 'cover_letter-docx' ? 'Exporting...' : 'Export cover letter (DOCX)'}</button>
        <button className="secondary-button" onClick={onInterviewPrep}>Prepare for Interview →</button>
      </div>
      {hasUnsavedEdits && saveStatus !== 'saving' && <p className="muted" role="status">You have unsaved edits. Exports use the last saved version.</p>}
      {saveError && <div className="error-notice" role="alert">{saveError}</div>}
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
        ? <button className="text-button" onClick={() => onStartMock(index)}>Practice this question →</button>
        : <>
          <textarea className="cover-letter-editor" aria-label="Your practice answer" value={mockState.draft} onChange={(event) => onAnswerChange(index, event.target.value)} rows={4} placeholder="Type your answer..." />
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

function InterviewPrepView({ resumeId, jobId, structuredResume, onSearchJobs, onUploadResume, onOpenApplication }: {
  resumeId: number | null
  jobId: string | null
  structuredResume: StructuredResume | null
  onSearchJobs: () => void
  onUploadResume: () => void
  onOpenApplication: (applicationId: number) => void
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
    if (resumeId === null || jobId === null || status === 'loading') return
    setStatus('loading'); setError(''); setMockAnswers({})
    try {
      const result = await generateInterviewPreparation(resumeId, jobId)
      setPrep(result)
      setVersions(await listInterviewPreparations(resumeId, jobId))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not generate interview preparation for this resume and opportunity.')
      // A timed-out or dropped request may still have completed on the server.
      void listInterviewPreparations(resumeId, jobId).then(setVersions).catch(() => undefined)
    }
  }

  const regenerate = async () => {
    if (resumeId === null || prep === null || status === 'loading') return
    setStatus('loading'); setError(''); setMockAnswers({})
    try {
      const result = await regenerateInterviewPreparation(resumeId, prep.id)
      setPrep(result)
      setVersions(await listInterviewPreparations(resumeId, prep.job_id))
      setStatus('idle')
    } catch (err: unknown) {
      setStatus('error')
      setError(err instanceof Error ? err.message : 'We could not regenerate interview preparation.')
      void listInterviewPreparations(resumeId, prep.job_id).then(setVersions).catch(() => undefined)
    }
  }

  const selectVersion = async (id: number) => {
    if (resumeId === null || id === prep?.id) return
    setError('')
    try {
      const full = await getInterviewPreparation(resumeId, id)
      if (full) { setPrep(full); setMockAnswers({}) }
    } catch (err: unknown) {
      setStatus('error'); setError(errorText(err, 'We could not load that version.'))
    }
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

  if (resumeId === null) return <><PageHeading eyebrow="Interview Prep" title="Prepare for your interview." lede="Categorized questions and a revision plan grounded in your resume and the opportunity you choose." /><EmptyState message="Upload and process your resume before preparing for an interview." action={<button className="secondary-button" onClick={onUploadResume}>Go to Resume Studio</button>} /></>
  if (jobId === null) return <><PageHeading eyebrow="Interview Prep" title="Prepare for your interview." lede="Select an opportunity to prepare for its interview." action={<button className="primary-button" onClick={onSearchJobs}>Search opportunities →</button>} /><EmptyState message={<>Open an opportunity's details, skill gap analysis, or customized application and choose “Prepare for Interview” to get started.</>} /></>

  const evidenceById: Record<string, EvidenceRecord> = {}
  if (prep) for (const record of prep.evidence) evidenceById[record.evidence_id] = record
  const structuredWarnings = structuredResume?.data.parser_warnings ?? []

  return <>
    <PageHeading
      eyebrow="INTERVIEW PREPARATION"
      title={prep ? `Preparing for ${prep.job_title}` : 'Generate your interview preparation.'}
      lede={prep ? `${prep.company} · version ${prep.version}${prep.stale ? ' · your resume has changed since this was generated' : ''}` : 'Categorized questions, preparation guidance and a revision plan grounded in your actual resume, profile and skill gaps.'}
      action={prep
        ? <button className="secondary-button" onClick={() => void regenerate()} disabled={status === 'loading'}>{status === 'loading' ? 'Regenerating...' : 'Regenerate →'}</button>
        : <button className="primary-button" onClick={() => void generate()} disabled={status === 'loading'}>{status === 'loading' ? 'Generating...' : 'Generate interview preparation →'}</button>}
    />
    {status === 'loading' && <LongTaskStatus label={prep ? 'Regenerating your interview preparation…' : 'Generating your interview preparation…'} detail="Building questions from this role's requirements and your resume evidence, then validating them. With an AI provider configured this can take up to a couple of minutes; results appear only after the server confirms them." />}
    {status === 'error' && <div className="error-notice" role="alert">{error}</div>}
    {structuredWarnings.length > 0 && <div className="architecture-note" role="status">Your resume was processed with parsing warnings — double-check resume-based questions below against your actual resume.</div>}

    {versions.length > 1 && <div className="tag-row">{versions.map((item) => <span key={item.id}><button className={`text-button ${prep?.id === item.id ? 'active' : ''}`} onClick={() => void selectVersion(item.id)}>v{item.version} · {GENERATION_LABEL[item.generation_mode]}{item.stale ? ' (stale)' : ''}</button></span>)}</div>}

    {prep && <>
      <TrackerLinkPanel kind="interview_preparation" jobId={prep.job_id} artifactId={prep.id} onOpenApplication={onOpenApplication} />
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
        ? <div className="success-notice" role="status">Grounding check passed — questions about your background reference only projects, skills and qualifications found in your resume/profile; other questions come from this role's requirements or your Skill Gap Analysis.</div>
        : <div className="error-notice" role="alert"><strong>{prep.validation.removed_claims.length > 0 ? 'Grounding warnings found — unsupported questions were removed.' : 'Grounding could not be confirmed.'}</strong><ul>{prep.validation.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></div>}

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

const STARTER_PROMPTS = [
  'Which opportunities fit my resume?', 'What skills am I missing?', 'Why does this job fit me?',
  'What should I learn next?', 'Help me customize my application.', 'Prepare me for an interview.',
]

function AssistantMessageBubble({ message, onAction }: { message: MessageOut; onAction: (action: SuggestedAction) => void }) {
  return <div className={`message ${message.role === 'user' ? 'user' : 'assistant'}`}>
    <span aria-hidden="true">{message.role === 'user' ? 'You' : 'AC'}</span>
    <span className="visually-hidden">{message.role === 'user' ? 'You said:' : 'Assistant said:'}</span>
    <div>
      {message.role === 'assistant' && message.generation && <span className={`skill-status ${GENERATION_TONE[message.generation.mode]} message-badge`}>{GENERATION_LABEL[message.generation.mode]}</span>}
      <p>{message.content}</p>
      {message.suggested_actions.length > 0 && <div className="message-actions">{message.suggested_actions.map((action, index) => <button key={`${action.action}-${index}`} onClick={() => onAction(action)}>{action.label} →</button>)}</div>}
    </div>
  </div>
}

function AssistantView({ resumeId, jobId, onAction }: { resumeId: number | null; jobId: string | null; onAction: (action: SuggestedAction) => void }) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [active, setActive] = useState<ConversationDetail | null>(null)
  const [listStatus, setListStatus] = useState<'idle' | 'loading' | 'error'>('loading')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [activeJobTitle, setActiveJobTitle] = useState('')

  const refreshList = async () => {
    const list = await listConversations()
    setConversations(list)
    return list
  }

  useEffect(() => {
    let cancelled = false
    setListStatus('loading')
    refreshList().then(async (list) => {
      if (cancelled) return
      if (list.length > 0) {
        const detail = await getConversation(list[0].id)
        if (!cancelled) setActive(detail)
      }
      setListStatus('idle')
    }).catch((reason: unknown) => { if (!cancelled) { setListStatus('error'); setError(reason instanceof Error ? reason.message : 'We could not load your conversations.') } })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    setActiveJobTitle('')
    if (!active?.active_job_id) return
    void getJobDetails(active.active_job_id).then((job) => { if (!cancelled) setActiveJobTitle(job.job_title) }).catch(() => {})
    return () => { cancelled = true }
  }, [active?.active_job_id])

  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [busyAction, setBusyAction] = useState(false)
  const messageEndRef = useRef<HTMLDivElement>(null)
  useEffect(() => { messageEndRef.current?.scrollIntoView({ block: 'nearest' }) }, [active?.messages.length, sending])
  // The skill graph's assistant ring tightens only while a message request is really pending.
  useEffect(() => {
    publishScene({ assistantPending: sending })
    return () => publishScene({ assistantPending: false })
  }, [sending])

  // Conversation actions report failures in the panel instead of failing silently.
  const runAction = async (action: () => Promise<void>, fallback: string) => {
    if (busyAction) return
    setBusyAction(true); setError('')
    try { await action() } catch (err: unknown) { setError(errorText(err, fallback)) } finally { setBusyAction(false) }
  }
  const selectConversation = (id: number) => runAction(async () => { setConfirmingDelete(false); setActive(await getConversation(id)) }, 'We could not open that conversation.')
  const startNewConversation = () => runAction(async () => {
    setConfirmingDelete(false)
    setActive(await createConversation(undefined, jobId ?? undefined))
    await refreshList()
  }, 'We could not start a new conversation.')
  const removeConversation = (id: number) => runAction(async () => {
    await deleteConversation(id)
    setConfirmingDelete(false)
    const list = await refreshList()
    if (active?.id === id) setActive(list.length > 0 ? await getConversation(list[0].id) : null)
  }, 'We could not delete this conversation.')

  const send = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    setSending(true); setError(''); setInput('')
    try {
      let conversation = active
      if (conversation === null) {
        conversation = await createConversation(undefined, jobId ?? undefined)
        setActive(conversation)
      }
      await sendMessage(conversation.id, trimmed, jobId ?? undefined)
      const updated = await getConversation(conversation.id)
      setActive(updated)
      await refreshList()
    } catch (err: unknown) {
      // Keep what the user typed so they can retry without retyping it.
      setInput((current) => current || trimmed)
      setError(errorText(err, 'We could not send your message. Please try again.'))
    } finally {
      setSending(false)
    }
  }

  const contextLine = `${active?.active_job_id ? `Opportunity: ${activeJobTitle || active.active_job_id}` : 'No opportunity selected yet'} · ${resumeId !== null ? 'Resume connected' : 'No processed resume yet'}`

  return <>
    <PageHeading eyebrow="Career Assistant" title="Guidance grounded in your profile." lede="Ask about your recommendations, skill gaps, resume, cover letter, or interview preparation." />
    <div className="assistant-layout">
      <section className="card assistant-panel" data-graph-anchor="">
        <div className="assistant-context"><span className="mini-icon">AI</span><div><strong>Career context</strong><small>{contextLine}</small></div></div>
        <div className="message-list" role="log" aria-live="polite" aria-label="Conversation">
          {active === null || active.messages.length === 0
            ? <div className="assistant-empty">
                <span className="assistant-mark">AC</span>
                <h3>Ask me anything about your career search.</h3>
                <p>I use your real resume, skill gaps, and job data — never invented facts.</p>
                <div className="starter-prompts">{STARTER_PROMPTS.map((prompt) => <button key={prompt} onClick={() => void send(prompt)} disabled={sending}>{prompt}</button>)}</div>
              </div>
            : active.messages.map((message) => <AssistantMessageBubble key={message.id} message={message} onAction={onAction} />)}
          {sending && <p className="muted typing-indicator" role="status"><span className="typing-dots" aria-hidden="true"><span /><span /><span /></span> Thinking…</p>}
          <div ref={messageEndRef} />
        </div>
        {error && <div className="error-notice" role="alert">{error}</div>}
        <form className="assistant-input" data-graph-keep-clear="" onSubmit={(event) => { event.preventDefault(); void send(input) }}>
          <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about your next step..." aria-label="Ask the career assistant" disabled={sending} />
          <button className="primary-button" disabled={sending || !input.trim()}>{sending ? 'Sending...' : 'Send'}</button>
        </form>
      </section>
      <aside className="assistant-quick card">
        <p className="eyebrow">CONVERSATIONS</p>
        <button className="secondary-button full-button" disabled={busyAction || sending} onClick={() => void startNewConversation()}>New conversation</button>
        {listStatus === 'loading' && <p className="muted" role="status">Loading conversations...</p>}
        <div className="conversation-list">
          {conversations.map((conversation) => <button key={conversation.id} className={`conversation-row ${active?.id === conversation.id ? 'active' : ''}`} aria-current={active?.id === conversation.id ? 'true' : undefined} disabled={busyAction} onClick={() => void selectConversation(conversation.id)}>
            <strong>{conversation.title || 'New conversation'}</strong>
            <small>{conversation.message_count} message{conversation.message_count === 1 ? '' : 's'}{conversation.active_job_id ? ` · ${conversation.active_job_id}` : ''}</small>
          </button>)}
          {conversations.length === 0 && listStatus === 'idle' && <p className="muted">No conversations yet.</p>}
        </div>
        {active !== null && (confirmingDelete
          ? <div className="confirm-row" role="group" aria-label="Confirm deletion"><span>Delete this conversation permanently?</span><button className="primary-button danger-button" disabled={busyAction} onClick={() => void removeConversation(active.id)}>{busyAction ? 'Deleting...' : 'Delete'}</button><button className="text-button" disabled={busyAction} onClick={() => setConfirmingDelete(false)}>Cancel</button></div>
          : <button className="text-button" onClick={() => setConfirmingDelete(true)}>Delete this conversation</button>)}
        <div className="aside-divider" />
        <p className="eyebrow">TRY ASKING</p>
        {STARTER_PROMPTS.slice(0, 4).map((prompt) => <button key={prompt} disabled={sending} onClick={() => void send(prompt)}>{prompt}<span aria-hidden="true">→</span></button>)}
      </aside>
    </div>
  </>
}
function ProgressView({ profile, resumeLifecycle, structuredResume }: { profile: CandidateProfile | null; resumeLifecycle: ResumeLifecycle; structuredResume: StructuredResume | null }) {
  const completion = profile ? profileCompletion(profile) : null
  const data = structuredResume?.data
  const resumeAnalyzed = resumeLifecycle === 'processed'
  return <>
    <PageHeading eyebrow="Progress" title="See your development clearly." lede="A focused view of what has genuinely been completed so far." />
    <section className="dashboard-stats">
      <Stat label="Profile completion" value={completion === null ? 'N/A' : `${completion.percent}%`} detail={completion ? `${completion.filled} of ${completion.total} profile details saved` : 'Profile not loaded yet'} />
      <Stat label="Resume analyzed" value={resumeAnalyzed ? 'Yes' : 'No'} detail={resumeAnalyzed ? 'Structured resume on file' : 'No resume processed yet'} />
      <Stat label="Skills extracted" value={String(data?.skills.length ?? 0)} detail="From your latest resume" />
      <Stat label="Projects extracted" value={String(data?.projects.length ?? 0)} detail="From your latest resume" />
    </section>
    <EmptyState message="Roadmap progress tracking is not implemented in this version. The figures above come directly from your saved profile and latest processed resume." />
  </>
}
const EMPTY_PROFILE: CandidateProfilePayload = { full_name: '', email: '', education: null, degree: null, specialization: null, experience_level: null, career_interests: [], target_roles: [], skills: [], career_goals: null }
function ProfileView({ profile, onProfileSaved }: { profile: CandidateProfile | null; onProfileSaved: (profile: CandidateProfile) => void }) {
  const toPayload = (source: CandidateProfile): CandidateProfilePayload => { const { id, created_at, updated_at, ...fields } = source; void id; void created_at; void updated_at; return fields }
  const [form, setForm] = useState<CandidateProfilePayload>(() => profile ? toPayload(profile) : EMPTY_PROFILE)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  useEffect(() => { setForm(profile ? toPayload(profile) : EMPTY_PROFILE) }, [profile])
  const updateText = (field: keyof CandidateProfilePayload) => (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => { const value = event.target.value || null; setForm((current) => ({ ...current, [field]: value })); setStatus('idle'); setMessage('') }
  const updateList = (field: 'career_interests' | 'target_roles' | 'skills') => (event: ChangeEvent<HTMLInputElement>) => { const items = event.target.value.split(',').map((item) => item.trim()).filter(Boolean); setForm((current) => ({ ...current, [field]: items })); setStatus('idle'); setMessage('') }
  const completion = profileCompletion(form).percent
  const loading = profile === null
  const save = async () => { if (profile === null) { setStatus('error'); setMessage('Your profile is not ready yet.'); return } if (!form.full_name.trim()) { setStatus('error'); setMessage('Full name is required.'); return } if (!/^\S+@\S+\.\S+$/.test(form.email)) { setStatus('error'); setMessage('Please enter a valid email address.'); return } setSaving(true); setStatus('idle'); setMessage(''); try { const savedProfile = await updateProfile(profile.id, form); onProfileSaved(savedProfile); setStatus('success'); setMessage('Profile saved.') } catch (error: unknown) { setStatus('error'); setMessage(error instanceof Error ? error.message : 'We could not save your profile. Please try again.') } finally { setSaving(false) } }
  return <><PageHeading eyebrow="Profile" title="Your structured context." lede="This information is combined with extracted resume data and passed to career services." action={<button className="primary-button" disabled={loading || saving} onClick={() => void save()}>{saving ? 'Saving...' : 'Save changes'}</button>} />{loading && <div className="architecture-note" role="status">Loading your saved profile...</div>}{!loading && status === 'error' && <div className="error-notice" role="alert">{message}</div>}{!loading && status === 'success' && <div className="success-notice" role="status">{message}</div>}<section className="profile-layout"><form className="card form-card" onSubmit={(event) => { event.preventDefault(); void save() }}><div className="card-heading"><div><p className="eyebrow">CORE DETAILS</p><h3>About you</h3></div><span className="completion-label">{completion}% complete</span></div><div className="form-grid"><label>Full name<input value={form.full_name} onChange={updateText('full_name')} disabled={loading || saving} /></label><label>Email address<input type="email" value={form.email} onChange={updateText('email')} disabled={loading || saving} /></label><label>Education<input value={form.education ?? ''} onChange={updateText('education')} disabled={loading || saving} /></label><label>Degree<input value={form.degree ?? ''} onChange={updateText('degree')} disabled={loading || saving} /></label><label>Specialization<input value={form.specialization ?? ''} onChange={updateText('specialization')} disabled={loading || saving} /></label><label>Experience level<input value={form.experience_level ?? ''} onChange={updateText('experience_level')} disabled={loading || saving} /></label><label>Career interests<input value={form.career_interests.join(', ')} onChange={updateList('career_interests')} disabled={loading || saving} /></label><label>Target roles<input value={form.target_roles.join(', ')} onChange={updateList('target_roles')} disabled={loading || saving} /></label><label>Skills<input value={form.skills.join(', ')} onChange={updateList('skills')} disabled={loading || saving} /></label><p className="field-hint full-width">Separate multiple career interests, target roles or skills with commas.</p><label className="full-width">Career goals<textarea value={form.career_goals ?? ''} onChange={updateText('career_goals')} disabled={loading || saving} /></label></div></form><aside className="card profile-aside"><p className="eyebrow">PROFILE STATUS</p><div className="profile-score"><strong>{completion}%</strong><span>{completion === 100 ? 'ready for guidance' : 'in progress'}</span></div><div className="progress-track"><span style={{ width: `${completion}%` }} /></div><p className="muted">Your saved profile and your latest analysed resume are used together when opportunities are matched and analysed.</p><div className="aside-divider" /><p className="eyebrow">PROFILE SECTIONS</p><ul className="check-list"><li className={form.full_name && form.email ? 'done' : ''}>Personal details{form.full_name && form.email ? <span className="visually-hidden"> (complete)</span> : null}</li><li className={form.career_interests.length ? 'done' : ''}>Career interests{form.career_interests.length ? <span className="visually-hidden"> (complete)</span> : null}</li><li className={form.education || form.degree ? 'done' : ''}>Education details{form.education || form.degree ? <span className="visually-hidden"> (complete)</span> : null}</li><li className={form.skills.length ? 'done' : ''}>Skills and technologies{form.skills.length ? <span className="visually-hidden"> (complete)</span> : null}</li><li className={form.target_roles.length || form.career_goals ? 'done' : ''}>Career direction{form.target_roles.length || form.career_goals ? <span className="visually-hidden"> (complete)</span> : null}</li></ul></aside></section></>
}
const formatBytes = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
const ACCEPTED_RESUME_TYPES = '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

function RealResumeView({ file, lifecycle, stage, restoring, notice, fileNotice, resumeRecord, onFileSelected, onClearFile, onAnalyze, onReprocess, onViewResults }: {
  file: File | null
  lifecycle: ResumeLifecycle
  stage: ResumeStage | null
  restoring: boolean
  notice: string
  fileNotice: string
  resumeRecord: ResumeRecord | null
  onFileSelected: (file: File | undefined) => void
  onClearFile: () => void
  onAnalyze: () => void
  onReprocess: () => void
  onViewResults: () => void
}) {
  const [dragging, setDragging] = useState(false)
  const busy = lifecycle === 'uploading' || lifecycle === 'processing'
  if (restoring) return <PageHeading eyebrow="Resume Studio" title="Upload and analyse your resume." lede="Checking for your most recently uploaded resume…" />
  const stageIndex = stage ? RESUME_STAGES.findIndex((item) => item.id === stage) : -1
  const stepState = (index: number): StepState => {
    if (busy) return index < stageIndex ? 'complete' : index === stageIndex ? 'active' : 'waiting'
    if (lifecycle === 'failed' && stageIndex >= 0) return index < stageIndex ? 'complete' : index === stageIndex ? 'failed' : 'waiting'
    if (lifecycle === 'processed' && !file) return 'complete'
    return 'waiting'
  }
  const fileInput = (text: string) => <label className="secondary-button file-button">{text}<input className="visually-hidden" type="file" accept={ACCEPTED_RESUME_TYPES} disabled={busy} onChange={(event: ChangeEvent<HTMLInputElement>) => { onFileSelected(event.target.files?.[0]); event.target.value = '' }} /></label>
  const onDrop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); setDragging(false); if (!busy) onFileSelected(event.dataTransfer.files[0]) }
  const statusText = busy ? `${RESUME_STAGES[stageIndex]?.label ?? 'Processing'}...` : lifecycle === 'processed' && !file ? 'Resume processed.' : ''
  return <>
    <PageHeading eyebrow="Resume Studio" title="Upload and analyse your resume." lede="We extract your skills, education, experience and projects from the file you upload. Everything shown across the workspace comes from it." action={lifecycle === 'processed' && !file ? <button className="secondary-button" onClick={onViewResults}>View analysis results</button> : undefined} />
    <section className="resume-layout">
      <div className="card upload-card">
        <div className="card-heading"><div><p className="eyebrow">Resume file</p><h2 className="card-title">{resumeRecord ? 'Your resume' : 'Upload your resume'}</h2></div><span className="file-support">PDF or DOCX · up to 10 MB</span></div>
        {resumeRecord && <div className="current-resume">
          <div><small>{lifecycle === 'processed' ? 'Active resume · analysed' : lifecycle === 'failed' ? 'Last upload · analysis failed' : lifecycle === 'awaiting_analysis' ? 'Uploaded · not analysed yet' : 'Current upload'}</small><strong>{resumeRecord.original_filename}</strong><small>{formatBytes(resumeRecord.file_size)} · uploaded {formatDateTime(resumeRecord.created_at)}</small></div>
          {lifecycle === 'processed' && <button className="text-button" onClick={onViewResults}>View results</button>}
        </div>}
        <div className={`drop-zone ${file ? 'has-file' : ''} ${dragging ? 'dragging' : ''}`} data-graph-keep-clear="" data-graph-anchor="" onDragOver={(event) => { event.preventDefault(); if (!busy) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
          <span className="upload-symbol" aria-hidden="true"><Icon name={file ? 'check' : 'upload'} /></span>
          {file
            ? <><strong>{file.name}</strong><p>{formatBytes(file.size)} · ready to upload and analyse</p>{!busy && <div className="drop-actions">{fileInput('Choose a different file')}<button className="text-button" onClick={onClearFile}>Remove</button></div>}</>
            : <><strong>{resumeRecord ? 'Upload a new version' : 'Drop your resume here'}</strong><p>Drag a file here, or choose one from your device.</p>{fileInput('Browse files')}<small>PDF or DOCX, up to 10 MB. Scanned images without selectable text cannot be read. Your current resume stays active until a new one is accepted.</small></>}
        </div>
        {fileNotice && <div className="error-notice" role="alert">{fileNotice}</div>}
        {notice && <div className="error-notice" role="alert"><div><strong>{lifecycle === 'failed' ? 'Analysis failed.' : 'Upload not accepted.'}</strong> {notice}{lifecycle === 'failed' && <> {resumeRecord && !file ? 'You can retry the analysis of this file, or upload a different one.' : 'Please choose a different file and try again.'}</>}</div></div>}
        {file && <button className="primary-button full-button" disabled={busy} aria-busy={busy} onClick={() => void onAnalyze()}>{busy ? <><span className="spinner" aria-hidden="true" />{statusText}</> : resumeRecord ? 'Upload and analyse new resume' : 'Upload and analyse'}</button>}
        {!file && resumeRecord && (lifecycle === 'processed' || lifecycle === 'failed' || lifecycle === 'awaiting_analysis' || busy) && <button className={`${lifecycle === 'awaiting_analysis' ? 'primary-button' : 'secondary-button'} full-button`} disabled={busy} aria-busy={busy} onClick={() => void onReprocess()}>{busy ? <><span className="spinner" aria-hidden="true" />{statusText}</> : lifecycle === 'failed' ? 'Retry analysis' : lifecycle === 'awaiting_analysis' ? 'Analyse this resume' : 'Reprocess this resume'}</button>}
      </div>
      <div className="card processing-card">
        <div className="card-heading"><div><p className="eyebrow">Analysis</p><h2 className="card-title">Processing steps</h2></div></div>
        <ol className="processing-steps" aria-label="Processing steps">{RESUME_STAGES.map((item, index) => <ProcessingStep key={item.id} label={item.label} state={stepState(index)} />)}</ol>
        <p className="visually-hidden" role="status" aria-live="polite">{statusText}</p>
        <p className="muted">Each step is a separate server request. A step is marked done only after the server confirms it — there is no simulated progress.</p>
      </div>
    </section>
  </>
}
function RealResumeResults({ structuredResume, lifecycle, resumeRecord, onNavigate, onReprocess }: { structuredResume: StructuredResume | null; lifecycle: ResumeLifecycle; resumeRecord: ResumeRecord | null; onNavigate: (view: View) => void; onReprocess: () => Promise<void> }) {
  const data = lifecycle === 'processed' ? structuredResume?.data : undefined
  const textOf = (item: Record<string, unknown>) => String(item.raw_text ?? item.title ?? '')
  const warnings = data?.parser_warnings ?? []
  const outdatedParser = warnings.some((warning) => warning.startsWith('outdated_parser_version'))
  const declaredSkills = new Set((data?.skills ?? []).map((skill) => skill.toLowerCase()))
  const projectTechnologies = [...new Set((data?.projects ?? []).flatMap((project) => Array.isArray(project.technologies) ? project.technologies.map(String) : []))].filter((tech) => !declaredSkills.has(tech.toLowerCase()))
  const hasExperienceHeading = (data?.sections ?? []).some((section) => section.name === 'experience' || section.name === 'internships')
  const list = (items: Array<Record<string, unknown>>, empty: string) => items.length > 0 ? <ul className="result-items">{items.map((item, index) => <li key={index}>{textOf(item)}</li>)}</ul> : <p className="muted">{empty}</p>
  const projects = data?.projects ?? []
  const excludedProjects = projects.filter((project) => project.evidence_eligible === false).length
  const languages = data?.languages ?? []
  const summary: Array<[number, string, string]> = data ? [
    [data.skills.length, 'skill', 'skills'], [projects.length, 'project', 'projects'], [data.education.length, 'education entry', 'education entries'],
    [data.certifications.length, 'certification', 'certifications'], [data.experience.length + data.internships.length, 'experience entry', 'experience entries'],
  ] : []
  return <>
    <PageHeading eyebrow="Resume Studio · Analysis results" title="What we extracted from your resume." lede={data && resumeRecord ? <>From <strong>{resumeRecord.original_filename}</strong>, processed by the resume parser. These are facts found in your file — review them against your actual resume.</> : 'Results appear here once a resume has been processed.'} action={<button className="secondary-button" onClick={() => onNavigate('resume')}>{data ? 'Upload a new version' : 'Go to Resume Studio'}</button>} />
    {!data ? <div className="architecture-note" role="status">{lifecycle === 'uploading' || lifecycle === 'processing' ? 'Your resume is still being processed.' : lifecycle === 'failed' ? 'Your latest resume could not be analysed, so there are no results to show. Open Resume Studio to retry or upload a different file.' : lifecycle === 'awaiting_analysis' ? 'Your latest resume was uploaded but has not been analysed yet. Open Resume Studio to analyse it.' : 'No resume has been analysed yet.'}</div> : <>
    {warnings.length > 0 && <div className="architecture-note" role="status"><div><strong>Processed with warnings</strong><p>{outdatedParser ? 'This resume was processed by an earlier version of the parser. Reprocess it to re-extract your stored file with the current parser — your original upload is kept.' : `Some parts of this resume's structure may need review — double-check the sections below against your actual resume.${excludedProjects > 0 ? ` ${excludedProjects} project ${excludedProjects === 1 ? 'entry looks' : 'entries look'} like parsing fragments and ${excludedProjects === 1 ? 'is' : 'are'} not used as evidence for recommendations or generated materials.` : ''}`}</p>{outdatedParser && <button className="secondary-button" onClick={() => void onReprocess()}>Reprocess with current parser</button>}</div></div>}
    <ul className="result-summary" aria-label="Extraction summary">{summary.map(([count, one, many]) => <li key={many}><strong>{count}</strong><span>{count === 1 ? one : many}</span></li>)}</ul>
    <section className="results-grid analysis-overview" aria-label="Analysis overview">
      <article className="card result-card"><h2 className="eyebrow">Sections found</h2>
        <ul className="coverage-list">{resumeCoverage(data).map((row) => <li key={row.key} className={row.found ? 'found' : 'absent'}><Icon name={row.found ? 'check' : 'minus'} />{row.label}<span className="visually-hidden">{row.found ? ': found' : ': not found'}</span></li>)}</ul>
        <p className="muted">A section counts as found when at least one entry was extracted from it. This describes what the parser read from your file, not the quality of your resume.</p>
      </article>
      <article className="card result-card"><h2 className="eyebrow">Strengths and gaps</h2>
        <p className="body-text">Strengths and gaps are measured against a specific opportunity’s requirements, so they appear in Skill Gaps for the role you choose — not as a general score for this resume.</p>
        <div className="detail-actions"><button className="primary-button" onClick={() => onNavigate('careers')}>Choose an opportunity</button></div>
      </article>
    </section>
    <div className="results-grid resume-result-grid">
      <article className="card result-card"><h2 className="eyebrow">EXTRACTED SKILLS</h2>{data.skills.length > 0 ? <div className="chip-list">{data.skills.map((skill) => <span className="skill-chip" key={skill}>{skill}</span>)}</div> : <p className="muted">No skills section found.</p>}{projectTechnologies.length > 0 && <><p className="muted">Also used in your projects:</p><div className="chip-list">{projectTechnologies.map((tech) => <span className="skill-chip" key={tech}>{tech}</span>)}</div></>}</article>
      <article className="card result-card"><h2 className="eyebrow">EDUCATION</h2>{data.education.length > 0 ? <ul className="result-items">{data.education.map((entry, index) => <li key={index}>{String(entry.raw_text ?? '')}{(entry.degree || entry.graduation_year) ? <span className="meta-badges">{typeof entry.degree === 'string' && entry.degree && <span className="meta-badge">{entry.degree}</span>}{typeof entry.graduation_year === 'number' && <span className="meta-badge">Graduation {entry.graduation_year}</span>}</span> : null}</li>)}</ul> : <p className="muted">No education entries extracted.</p>}</article>
      <article className="card result-card"><h2 className="eyebrow">EXPERIENCE AND INTERNSHIPS</h2>{list([...data.experience, ...data.internships], hasExperienceHeading ? 'An experience section was found, but no entries could be extracted from it.' : 'Your resume has no work experience or internship section.')}</article>
      <article className="card result-card result-card-wide"><h2 className="eyebrow">PROJECTS</h2>{projects.length > 0 ? <ul className="project-entries">{projects.map((project, index) => {
        const technologies = Array.isArray(project.technologies) ? project.technologies.map(String) : []
        const description = String(project.description ?? '')
        return <li className={`project-entry${project.evidence_eligible === false ? ' excluded' : ''}`} key={index}>
          <div className="project-entry-head"><h3>{String(project.title ?? '') || 'Untitled project'}</h3>{project.evidence_eligible === false && <span className="evidence-badge" title="This entry looks like a parsing fragment, so recommendations and generated materials do not use it.">Not used as evidence</span>}</div>
          {technologies.length > 0 && <div className="chip-list" aria-label="Technologies">{technologies.map((tech) => <span className="skill-chip" key={tech}>{tech}</span>)}</div>}
          {description && <p>{description}</p>}
        </li>
      })}</ul> : <p className="muted">No projects extracted.</p>}</article>
      {data.summary && <article className="card result-card"><h2 className="eyebrow">SUMMARY</h2><p className="body-text">{data.summary}</p></article>}
      {data.certifications.length > 0 && <article className="card result-card"><h2 className="eyebrow">CERTIFICATIONS</h2>{list(data.certifications, '')}</article>}
      {data.achievements.length > 0 && <article className="card result-card"><h2 className="eyebrow">ACHIEVEMENTS</h2>{list(data.achievements, '')}</article>}
      {languages.length > 0 && <article className="card result-card"><h2 className="eyebrow">LANGUAGES</h2><div className="chip-list">{languages.map((entry, index) => <span className="skill-chip" key={index}>{String(entry.raw_text ?? '')}</span>)}</div></article>}
      {data.qualifications.length > 0 && <article className="card result-card"><h2 className="eyebrow">QUALIFICATIONS</h2>{list(data.qualifications, '')}</article>}
    </div>
    <div className="detail-actions"><button className="primary-button" onClick={() => onNavigate('careers')}>See matching opportunities →</button><button className="secondary-button" onClick={() => onNavigate('profile')}>Review career profile</button></div>
  </>}</>
}
type StepState = 'waiting' | 'active' | 'complete' | 'failed'
const STEP_TEXT: Record<StepState, string> = { waiting: 'Waiting', active: 'In progress', complete: 'Done', failed: 'Failed' }
function ProcessingStep({ label, state }: { label: string; state: StepState }) { return <li className={`processing-step ${state}`}><span className={`process-icon ${state}`} aria-hidden="true">{state === 'complete' ? '✓' : state === 'failed' ? '!' : state === 'active' ? <span className="spinner" /> : ''}</span><strong>{label}</strong><span className="step-text">{STEP_TEXT[state]}</span></li> }
function SettingsView() { return <><PageHeading eyebrow="Settings" title="Keep your workspace focused." lede="Manage the preferences that shape your career companion experience." /><section className="settings-list"><article className="card setting-row"><div><strong>Profile preferences</strong><p>Your saved career interests and target roles guide the recommendations shown to you.</p></div><span className="planned-tag">ACTIVE</span></article><article className="card setting-row"><div><strong>Data connection</strong><p>Your profile, resume analysis, opportunity search and matching, skill gap analysis, resume and cover letter customization, interview preparation, the AI career assistant and the application tracker are all backed by the AI Career Companion API. The learning roadmap is not available yet.</p></div><span className="planned-tag">ACTIVE</span></article><article className="card setting-row"><div><strong>Privacy</strong><p>Your resume file, extracted profile data and application tracker entries are stored by the AI Career Companion backend. When an external AI language model is configured for this workspace, relevant excerpts of your resume and profile, together with the selected opportunity (and, for the assistant, your recent chat messages), are sent to that provider to help write tailored materials, interview preparation and assistant replies; otherwise these features run without any external AI service. Your uploaded resume file itself is not sent.</p></div><span className="planned-tag">ACTIVE</span></article></section></> }

export default App
