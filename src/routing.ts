// URL ⇄ view mapping for the History API router in App. Pure functions of a location so
// they can be unit-tested; callers pass `window.location` (the default).

export type View = 'dashboard' | 'profile' | 'resume' | 'resume-results' | 'careers' | 'job-details' | 'skills' | 'customize' | 'interview-prep' | 'roadmap' | 'assistant' | 'progress' | 'settings' | 'applications' | 'application-details'

type LocationLike = Pick<Location, 'pathname' | 'search'>

export type NavGroup = 'Workspace' | 'Growth' | 'You'
export type NavIcon = 'overview' | 'resume' | 'opportunities' | 'applications' | 'skills' | 'roadmap' | 'interview' | 'assistant' | 'profile' | 'progress' | 'settings'
export type NavItem = { id: View; label: string; note: string; group: NavGroup; icon: NavIcon }

// Primary navigation, grouped. Every id is an existing route (path = /<id>); labels follow
// the product's information architecture. Settings is listed separately.
export const nav: NavItem[] = [
  { id: 'dashboard', label: 'Overview', note: 'Status and next steps', group: 'Workspace', icon: 'overview' },
  { id: 'resume', label: 'Resume Studio', note: 'Upload and analysis', group: 'Workspace', icon: 'resume' },
  { id: 'careers', label: 'Opportunities', note: 'Search and matches', group: 'Workspace', icon: 'opportunities' },
  { id: 'applications', label: 'Applications', note: 'Statuses and deadlines', group: 'Workspace', icon: 'applications' },
  { id: 'skills', label: 'Skill Gaps', note: 'Requirement-by-requirement', group: 'Growth', icon: 'skills' },
  { id: 'roadmap', label: 'Learning Roadmap', note: 'Your learning path', group: 'Growth', icon: 'roadmap' },
  { id: 'interview-prep', label: 'Interview Prep', note: 'Questions and practice', group: 'Growth', icon: 'interview' },
  { id: 'assistant', label: 'Career Assistant', note: 'Contextual guidance', group: 'Growth', icon: 'assistant' },
  { id: 'profile', label: 'Profile', note: 'Your career context', group: 'You', icon: 'profile' },
  { id: 'progress', label: 'Progress', note: 'What you have completed', group: 'You', icon: 'progress' },
]
export const SETTINGS_ITEM: NavItem = { id: 'settings', label: 'Settings', note: 'Workspace preferences', group: 'You', icon: 'settings' }
export const NAV_GROUPS: NavGroup[] = ['Workspace', 'Growth', 'You']

// The navigation entry a screen belongs to, so sub-pages keep their section highlighted.
export const navSection = (view: View): View => view === 'resume-results' ? 'resume' : view === 'job-details' || view === 'customize' ? 'careers' : view === 'application-details' ? 'applications' : view

// Job-scoped screens (skill gap, customization, interview prep) carry the selected
// opportunity in the URL (?job=...) so a refresh or a shared link reopens the same
// persisted analysis instead of losing the selection held only in memory.
export const JOB_SCOPED_VIEWS: View[] = ['skills', 'customize', 'interview-prep']

// Paths that belong to the signed-out screens; signing in from one of them continues to the dashboard.
export const AUTH_PATHS = ['/', '/login', '/signup', '/onboarding']

export const jobIdFromLocation = (location: LocationLike = window.location): string | null =>
  location.pathname.startsWith('/jobs/') ? decodeURIComponent(location.pathname.slice('/jobs/'.length)) || null : new URLSearchParams(location.search).get('job')

export const applicationIdFromLocation = (location: LocationLike = window.location): number | null => {
  const match = /^\/applications\/(\d+)$/.exec(location.pathname)
  return match ? Number(match[1]) : null
}

export const viewFromLocation = (location: LocationLike = window.location): View => {
  const path = location.pathname
  if (path.startsWith('/jobs/')) return 'job-details'
  if (path.startsWith('/applications/')) return 'application-details'
  if (path === '/resume/results') return 'resume-results'
  if (path === '/customize') return 'customize'
  if (path === '/interview-prep') return 'interview-prep'
  const match = nav.find((item) => `/${item.id}` === path)
  return match?.id ?? (path === '/settings' ? 'settings' : 'dashboard')
}

// Everything the router derives from a URL. Used on first load, on back/forward, and
// when a session is re-established, so the screen and its selection always agree.
export const routeFromLocation = (location: LocationLike = window.location) => ({
  view: viewFromLocation(location),
  jobId: jobIdFromLocation(location),
  applicationId: applicationIdFromLocation(location),
})

export const pathForView = (view: View, jobId: string | null, applicationId: number | null): string => {
  const query = JOB_SCOPED_VIEWS.includes(view) && jobId ? `?job=${encodeURIComponent(jobId)}` : ''
  const base = view === 'job-details' ? `jobs/${jobId ?? ''}` : view === 'application-details' ? `applications/${applicationId ?? ''}` : view === 'resume-results' ? 'resume/results' : view
  return `/${base}${query}`
}

export const viewLabel = (view: View) => nav.find((item) => item.id === view)?.label ?? (view === 'job-details' ? 'Opportunity' : view === 'resume-results' ? 'Analysis results' : view === 'customize' ? 'Application materials' : view === 'application-details' ? 'Application' : 'Settings')
