# Career Opportunity Dataset & Knowledge Base

This folder contains the curated sample dataset for the AI Career Companion project.

Originally built for Milestone 2.1 as an internship-only dataset (`internship_jobs_180.json`,
180 records), and expanded for the "Career Opportunity Generalization" enhancement to
cover the broader set of early-career opportunity types students actually apply to —
see [`docs/CAREER_OPPORTUNITY_GENERALIZATION.md`](../../../docs/CAREER_OPPORTUNITY_GENERALIZATION.md)
for the full rationale and audit.

## Deliverables
- `job_posting_schema.json` — canonical posting schema (schema_version 1.1).
- `career_opportunities_320.json` — canonical backend/RAG dataset (320 records).
- `career_opportunities_320.csv` — tabular inspection copy.
- `validation_report.json` — quality validation results.

## Quality summary
- Records: 320 (180 original internship-era records, unchanged, + 140 new records)
- Domains: 15
- Missing required values: 0
- Duplicate IDs: 0
- Duplicate content: 0
- Validation: PASS

## Opportunity types (`employment_type`)
| Type | Count | Share |
| --- | --- | --- |
| Internship | 170 | 53% |
| Entry Level | 80 | 25% |
| Graduate Role | 45 | 14% |
| Trainee | 15 | 5% |
| Apprenticeship | 10 | 3% |

## Dataset policy
The records are synthetic curated samples for academic development and evaluation.
They are not live vacancies and must not be shown to users as current openings.

## M2.2 handoff
Use `career_opportunities_320.json` as the source of truth.
Use `job_id` as the stable parent document ID when generating chunks so retrieved chunks can map back to the complete posting.
