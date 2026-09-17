# Milestone 2.3 — Job-Resume Matching Agent

The matching service consumes the existing structured resume JSON and profile fields, constructs a concise retrieval query, reuses M2.2 semantic search, and scores only the retrieved candidate jobs.

## Flow

Structured resume -> normalized profile -> retrieval query -> M2.2 semantic retrieval -> candidate jobs -> deterministic component scoring -> explanation -> match ranking

`retrieval_score` remains M2.2 semantic relevance. `match_score` is a separate 0-100 compatibility score and is the primary ranking key.

## Score weights

- Required skills: 35%
- Preferred skills: 15%
- Experience: 15%
- Education: 10%
- Project/domain relevance: 15%
- Qualifications/general fit: 10%

Weights are defined in `app/services/job_matching.py`. If a job has no preferred skills, that component scores 1.0. If student evidence is unavailable for education, projects, or qualifications, that component is excluded and the remaining weights are re-normalized. Missing specified required skills are never hidden by retrieval relevance.

Skill comparison uses exact normalized terms and a small explicit alias map. Education and experience use conservative rule-based checks. Explanations, strengths, and gaps are generated only from computed evidence; no LLM is used.

## API

```text
GET /api/resumes/{resume_id}/job-matches?top_k=10
```

The resume must already have a persisted structured-resume record. The endpoint returns `retrieval_score`, `match_score`, component scores, matched/missing skills, relevant projects, strengths, gaps, and deterministic reasoning.

M2.3 does not implement retrieval evaluation, precision/recall dashboards, or M2.4 benchmark reporting.
