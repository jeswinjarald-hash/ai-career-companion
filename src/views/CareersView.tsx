import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { EmptyState, PageHeading } from '../components/common'
import { errorText } from '../lib/errorText'
import { searchJobs, type JobSearchResult } from '../services/jobService'
import { MATCH_SCORE_DEFINITION } from '../lib/insights'
import { getJobMatches, type JobMatchResult } from '../services/resumeService'

export function CareersView({ resumeId, onOpenJob, onUploadResume }: { resumeId: number | null; onOpenJob: (jobId: string) => void; onUploadResume: () => void }) {
  const [matches, setMatches] = useState<JobMatchResult[] | null>(null)
  const [matchError, setMatchError] = useState('')
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState<JobSearchResult[] | null>(null)
  const [searchStatus, setSearchStatus] = useState<'idle' | 'loading' | 'error'>('idle')
  const [searchError, setSearchError] = useState('')

  const [matchReload, setMatchReload] = useState(0)

  // Matches always belong to the current resume: clear the previous result first so a
  // different resume's ranking is never shown while the new one loads (or fails).
  useEffect(() => {
    let cancelled = false
    setMatches(null); setMatchError('')
    if (resumeId === null) return
    void getJobMatches(resumeId).then((result) => { if (!cancelled) setMatches(result) }).catch((reason: unknown) => { if (!cancelled) setMatchError(errorText(reason, 'We could not load recommendations.')) })
    return () => { cancelled = true }
  }, [resumeId, matchReload])

  const runSearch = async (event: FormEvent) => {
    event.preventDefault()
    if (!query.trim() || searchStatus === 'loading') return
    setSearchStatus('loading'); setSearchError(''); setSearchResults(null)
    try {
      const results = await searchJobs(query.trim(), 10)
      setSearchResults(results)
      setSearchStatus('idle')
    } catch (error: unknown) {
      setSearchStatus('error')
      setSearchError(error instanceof Error ? error.message : 'We could not search opportunities. Please try again.')
    }
  }

  return <>
    <PageHeading eyebrow="Opportunities" title="Paths that fit your profile." lede="Search internships, entry-level jobs, graduate programs, and trainee/apprenticeship roles, or review recommendations ranked from your latest resume." />
    <section className="card comparison-card">
      <div className="card-heading"><div><p className="eyebrow">SEMANTIC OPPORTUNITY SEARCH</p><h3>Search opportunities</h3></div></div>
      <form className="assistant-input" onSubmit={(event) => void runSearch(event)}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='e.g. "Python machine learning internship" or "graduate data analyst"' aria-label="Search opportunities" />
        <button className="primary-button" disabled={searchStatus === 'loading'}>{searchStatus === 'loading' ? 'Searching...' : 'Search'}</button>
      </form>
      {searchStatus === 'error' && <div className="error-notice" role="alert">{searchError}</div>}
      {searchStatus !== 'error' && searchResults !== null && searchResults.length === 0 && <p className="muted">No opportunities matched that search.</p>}
      {searchResults !== null && searchResults.some((result) => result.query_confidence === 'unsupported_area') && <div className="architecture-note" role="status">Few of your search terms appear in the opportunities available here, so these closest results may not match what you are looking for.</div>}
      {/* The backend score is the cosine similarity of the best-matching section of an
          opportunity plus 0.05 x the similarity of each other matching section
          (job_search_service.py). It has no fixed maximum, so it is shown as an ordering
          and a raw score — never as a percentage. */}
      {searchResults !== null && searchResults.length > 0 && <p className="muted card-intro">Ordered from most to least similar to your search. The similarity score compares your search with each opportunity's text; it has no fixed maximum and is not a match percentage.</p>}
      {searchResults !== null && searchResults.length > 0 && <section className="career-list">
        {searchResults.map((result, index) => <article className="card career-card" data-graph-magnet="" key={result.job_id}>
          <div className="career-card-top"><span className="role-mark">{result.job_title.slice(0, 1)}</span><span className="match-badge">Rank {index + 1} of {searchResults.length}</span></div>
          <h3>{result.job_title}</h3>
          <div className="tag-row"><span className="opportunity-type-chip">{result.employment_type}</span></div>
          <p>{result.company} · {result.domain} · {result.location} · {result.work_mode}</p>
          <p className="muted">Similarity score {result.similarity_score.toFixed(2)}</p>
          <div className="tag-row">{result.required_skills.slice(0, 4).map((skill) => <span key={skill}>{skill}</span>)}</div>
          <button className="text-button" onClick={() => onOpenJob(result.job_id)}>View details →</button>
        </article>)}
      </section>}
    </section>
    <section className="card comparison-card">
      <div className="card-heading"><div><p className="eyebrow">RECOMMENDED FOR YOUR RESUME</p><h3>Ranked from your latest processed resume</h3></div></div>
      {resumeId !== null && matches !== null && matches.length > 0 && <p className="muted card-intro">Retrieved by semantic search (Sentence Transformers + FAISS), then scored against your resume and profile. {MATCH_SCORE_DEFINITION}</p>}
      {matchError ? <div className="error-notice" role="alert">{matchError} <button className="text-button" onClick={() => setMatchReload((value) => value + 1)}>Retry</button></div>
        : resumeId === null ? <EmptyState message="Process a resume to see opportunities ranked for you." action={<button className="secondary-button" onClick={onUploadResume}>Go to Resume Studio</button>} />
        : matches === null ? <p className="muted" role="status">Ranking opportunities against your resume...</p>
        : matches.length === 0 ? <EmptyState message="No opportunities in the current catalogue matched your resume. Try a semantic search above." />
        : <section className="career-list">{matches.map((match) => <article className="card career-card" data-graph-magnet="" key={match.job_id}><div className="career-card-top"><span className="role-mark">{match.job_title.slice(0, 1)}</span><span className="match-badge" title="Weighted score from required and preferred skills, experience, education, projects and qualifications.">{Math.round(match.match_score)}% match</span></div><h3>{match.job_title}</h3><div className="tag-row"><span className="opportunity-type-chip">{match.employment_type}</span></div><p>{match.company} · {match.domain}</p><div className="tag-row">{match.matched_required_skills.slice(0, 3).map((skill) => <span key={skill}>{skill}</span>)}</div><p className="muted">{match.reasoning}</p><p className="result-bullet">Missing required skills: {match.missing_required_skills.join(', ') || 'none'}</p><button className="text-button" onClick={() => onOpenJob(match.job_id)}>View details →</button></article>)}</section>}
    </section>
  </>
}
