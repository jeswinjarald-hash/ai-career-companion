# Milestone 2.1 — Internship Dataset & Knowledge Base

This folder contains the curated sample dataset for the AI Career Companion project.

## Deliverables
- `job_posting_schema.json` — canonical job-posting schema.
- `internship_jobs_180.json` — canonical backend/RAG dataset.
- `internship_jobs_180.csv` — tabular inspection copy.
- `validation_report.json` — quality validation results.

## Quality summary
- Records: 180
- Domains: 15
- Missing required values: 0
- Duplicate IDs: 0
- Duplicate content: 0
- Validation: PASS

## Dataset policy
The records are synthetic curated samples for academic development and evaluation.
They are not live vacancies and must not be shown to users as current openings.

## M2.2 handoff
Use `internship_jobs_180.json` as the source of truth.
Use `job_id` as the stable parent document ID when generating chunks so retrieved chunks can map back to the complete job posting.
