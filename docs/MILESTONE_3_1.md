# Milestone 3.1 — Skill Gap Analysis Agent

The Skill Gap Analysis Agent compares a student's structured resume/profile against a
selected internship and produces a grounded, evidence-backed report: what is already
demonstrated, what is missing, what is only partially demonstrated, and what to do about
each gap. No LLM is used — every classification, score, and recommendation is produced
by deterministic code, the same architectural choice this project already made for the
Milestone 2.3 job-matching agent (`app/services/job_matching.py`).

## Flow

```
Candidate profile + structured resume (M1)
        +
Selected internship (M2 job dataset, chosen from search or a Job Match result)
        v
Evidence extraction  (app/services/skill_gap_evidence.py)
        v
Requirement classification: demonstrated / partial / missing
        v
Deterministic readiness scoring
        v
Template-based, job-grounded recommendations
        v
Persisted SkillGapAnalysis  (app/services/skill_gap_service.py)
```

## Reused from Milestone 1 / 2 (not rebuilt)

- Structured resume shape and skill canonicalization (`app.services.structured_resume`).
- Term/alias normalization: `app.services.job_matching.normalize_term`, so a skill like
  "JS" or "fast api" normalizes identically whether it's being job-matched or skill-gap
  analyzed.
- Job dataset access: `app.services.job_dataset_service.load_job_postings`.
- Auth/ownership: `require_current_user`, `get_owned_resume` (a user can never analyze
  another user's resume).
- Persistence table: the existing (previously unused) `skill_gaps` SQLAlchemy model in
  `app/models/career_state.py` — no new table or migration was needed.
- Frontend: existing CSS classes (`.result-card`, `.skill-status`, `.mini-gap`,
  `.recommendation-line`, `.chip-list`, ...) and the existing typed-fetch service pattern
  (`src/services/*.ts`).

## Evidence extraction and matching (`skill_gap_evidence.py`)

Every job requirement is matched against a list of `EvidenceUnit`s built from real student
data only: profile skills, resume skills section, project titles/descriptions/technologies,
experience entries, internship entries, certifications, achievements, listed qualifications,
career goals, and education (profile fields + resume education section). Nothing is
invented — a requirement with no matching evidence unit is reported as `missing`.

Matching is layered:

1. **Exact/alias match** — the normalized requirement term is either an explicitly declared
   skill (profile skills, resume skills section, a project's technologies) or is mentioned
   verbatim in free-text evidence (e.g. "Developed REST APIs using FastAPI" satisfies a
   "FastAPI" requirement even with no dedicated technologies list). -> `demonstrated`.
2. **Related-but-not-equivalent match** — `RELATED_TERMS` is a curated map of technologies
   that are conceptually related but must never be treated as the same skill (PyTorch is
   never satisfied by TensorFlow evidence, AWS is never satisfied by Azure evidence, MySQL
   is never satisfied by MongoDB evidence, and so on). A hit here can only ever produce
   `partial`, and the evidence names the specific related technology that was actually
   found so the student is never misled into thinking they have the exact skill.
3. **No evidence** -> `missing`.

Confidence is a small set of fixed, documented values per branch (0.95 for an explicit
skills-list match, 0.85 for a free-text mention, 0.6 for a related-technology partial
match, 0.95 for missing) — never an LLM-guessed number.

## Requirement categories

| Category | Source | Unmet outcome |
| --- | --- | --- |
| Strengths | any requirement matched `demonstrated` | — |
| Critical gaps | `job.required_skills`, `missing` | `critical_gaps`, priority high |
| Partial gaps | `job.required_skills`, `partial` | `partial_gaps`, priority medium |
| Preferred skill gaps | `job.preferred_skills`, not demonstrated | `preferred_gaps`, priority low |
| Experience gaps | `job.experience_requirements` | `experience_gaps`, high/medium |
| Qualification gaps | `job.qualifications` + education requirement | `qualification_gaps`, medium/low |

Required-skill gaps are always kept separate from preferred-skill gaps so a student is
never misled into thinking an optional skill is a blocker.

### Experience

`assess_experience` distinguishes professional/internship evidence from academic/personal
project evidence, per the spec's own guidance that a project should not silently satisfy a
"1 year of professional experience" requirement. A quantified requirement ("1+ years") is
checked against explicit year mentions in experience/internship text; project-only evidence
for a quantified requirement is `partial`, never `demonstrated`.

### Education

`assess_education` distinguishes "no education evidence available" (component excluded
from the readiness score — a data-entry gap, not a job-fit gap) from "education evidence
present but does not match the stated field" (`partial`/`missing`, scored).

### Qualifications

The real job dataset's `qualifications` field is mostly free-text behavioral/soft-skill
expectations ("Strong problem-solving and analytical ability"). These are matched
conservatively (exact-phrase evidence only) and, per the hallucination-protection
requirement, an unmet one is reported as *"Insufficient evidence to confirm this from the
current resume/profile"* rather than a hard claim of absence, with low priority and a
recommendation to prepare a concrete example rather than "learn" an unlearnable trait.

## Readiness scoring

A separate, explicitly-labeled score from the Milestone 2 job **match score** — this one
measures requirement-by-requirement readiness, not semantic retrieval relevance.

```
READINESS_WEIGHTS = {
    "required_skills": 0.40,
    "preferred_skills": 0.15,
    "experience":       0.20,
    "education":        0.10,
    "qualifications":   0.15,
}
```

Each component's score is `(demonstrated_count + 0.5 * partial_count) / total`. A
component with no applicable requirements (e.g. a job has no preferred skills) is excluded
and the remaining weights are renormalized — the same pattern M2.3 already uses. The final
`overall_readiness` is a rounded integer percentage; the full per-component breakdown
(`score_breakdown`) is returned so the number is always explainable, never a black box.

## Hallucination protection

- Every strength and gap carries `student_evidence`, a list of `{source, source_name,
  evidence}` citations traceable to real resume/profile content.
- A missing requirement's evidence list is always empty and its reason is the fixed string
  `"No explicit evidence found in the current resume/profile."`
- A related-technology partial match explicitly names the related technology found, so the
  student is never told they have a skill they don't.
- Recommendations are template-based and reference only the job's own stated title,
  company, and requirement text — never a fabricated statistic, metric, or achievement.
- `test_full_pipeline_produces_grounded_real_data_analysis_and_persists` (backend tests)
  asserts every requirement string appearing anywhere in a real analysis result is a subset
  of the real job posting's own required/preferred/qualification/experience/education
  fields — nothing is fabricated.

## API

```
POST /api/resumes/{resume_id}/skill-gap?job_id=JOB-0035
GET  /api/resumes/{resume_id}/skill-gap/{job_id}
```

`POST` re-runs the deterministic analysis (cheap — no LLM/network call) and upserts the
persisted result. `GET` returns the last persisted result without recomputing, with `stale`
set to `true` if the student's structured resume has been reprocessed since that analysis
was generated. Both require authentication and verify the resume belongs to the current
user (`get_owned_resume`); a resume without a structured record returns `409`; an unknown
job or resume returns `404`.

## Persistence

Reuses the existing `skill_gaps` table (`user_id`, `job_id` unique together) —
`data` stores the full `SkillGapAnalysis` JSON payload, including `resume_id` and
`resume_updated_at` for staleness comparison. No schema migration was required.

## Frontend

`src/services/skillGapService.ts` follows the existing typed-fetch-wrapper pattern
(`ResumeApiError`-style). The Job Details page (already showing the Milestone 2 match
score) gains an **"Analyze Skill Gaps"** action that navigates to the Skill Gap Analysis
page with the selected job carried over — no manual ID entry. The Skill Gap Analysis page
renders real backend data only: readiness score with an explicit breakdown, strengths,
critical/partial/preferred/experience/qualification gap sections (each gap card shows
importance, evidence or the reason it's missing, and a concrete recommendation), and a
priority-ordered improvement plan. Empty states ("upload a resume first", "select an
internship first"), loading, and error states are all handled — nothing renders fake data.

## Tests

- `backend/tests/test_skill_gap_evidence.py` — exact/alias matching, missing-skill
  handling, related-but-different-technology partial matching (PyTorch/TensorFlow,
  AWS/Azure, React/Angular, MySQL/MongoDB), free-text evidence detection, determinism.
- `backend/tests/test_skill_gap_service.py` — full `analyze_skill_gap` against real job
  dataset entries, preferred-vs-critical separation, experience/education assessment
  branches, score determinism, persisted-analysis staleness detection.
- `backend/tests/test_skill_gap_api.py` — authentication required, ownership enforced
  (a second user cannot analyze or read another user's resume), 404/409 error states, and
  a full real-pipeline test (upload -> extract -> section-detect -> structure -> analyze)
  asserting every reported requirement traces back to the real job posting's own fields.
