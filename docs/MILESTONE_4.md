# Milestone 4 — Application Tracking, Evaluation, Optimization and Release

Milestone 4 has four parts. This document describes **M4.1** in full and points to the
canonical artifacts for the other three, so that evaluation evidence is not duplicated.

| Part | Scope | Canonical artifact |
|---|---|---|
| M4.1 | Application tracker | this document |
| M4.2 | Baseline evaluation of the full workflow | [`backend/data/evaluation/m4/README.md`](../backend/data/evaluation/m4/README.md), `results/M4_2_BASELINE_REPORT.md`, `results/m4_2_baseline_results.json` (frozen) |
| M4.3 | Controlled optimization against the frozen baseline | `results/M4_3_OPTIMIZATION_REPORT.md`, `results/m4_3_experiments.json`, `results/m4_3_optimized_results.json` |
| M4.4 | Final documentation, demo preparation, release audit | [`FINAL_TECHNICAL_DOCUMENTATION.md`](FINAL_TECHNICAL_DOCUMENTATION.md) §19–§30 |

## M4.1 — Application Tracker

### Purpose

Let a student keep every application in one place: opportunities found in Careers and
applications made elsewhere, with status, the dates the student enters, interview
details, notes, and the resume / cover letter / interview preparation generated for that
job. All logic is plain database querying and deterministic date rules — no embeddings,
FAISS or LLM.

### Files

| File | Role |
|---|---|
| `backend/app/models/application.py` | `applications` table |
| `backend/app/schemas/application.py` | Status/source/sort/reminder literals (single source of truth), request/response models, summary and reminder schemas |
| `backend/app/services/application_service.py` | Create (dataset snapshot or manual), update, delete, list/filter/sort, summary, reminders, artifact validation |
| `backend/app/api/applications.py` | `/api/applications` router (maps service errors to HTTP) |
| `src/services/applicationService.ts` | Typed API client |
| `src/components/applications/*` | Tracker list, detail/edit view, dashboard widgets, formatting helpers, styles |
| `src/App.tsx` | Routes `/applications` and `/applications/{id}`; "Add to Tracker" on job details, customization and interview prep pages; dashboard "Application activity" block |
| `backend/tests/test_application_service.py`, `backend/tests/test_applications_api.py` | Service and API tests (incl. ownership) |

### Data model (`applications`)

| Column | Notes |
|---|---|
| `user_id` | Owner (FK `users.id`), indexed |
| `source` | `dataset` (tracked from Careers) or `manual` |
| `job_id` | Canonical `JOB-xxxx` for dataset rows; NULL for manual rows |
| `company`, `job_title`, `employment_type`, `location`, `work_mode`, `job_description` | Snapshot. For dataset rows it is copied **server-side** from the canonical dataset at creation and is not later changed by the client; for manual rows it is what the user typed |
| `status`, `status_updated_at` | Lifecycle (below); timestamp reset on each status change |
| `applied_date`, `deadline`, `follow_up_date` | Calendar dates entered by the user |
| `interview_at`, `interview_status` | Timezone-aware instant stored in UTC; `scheduled` / `completed` / `cancelled` |
| `notes` | Free text |
| `customization_id`, `interview_preparation_id` | Optional links to generated materials |
| `created_at`, `updated_at` | UTC timestamps |

Constraint: unique (`user_id`, `job_id`). Because NULLs are distinct, a canonical job can
be tracked once per user (a second attempt returns **409**), while manual rows are
unlimited.

**Deadlines are never inferred.** The opportunity dataset contains no deadlines; every
date in the tracker is supplied by the student.

### Status lifecycle

`saved`, `planning`, `applied`, `under_review`, `shortlisted`, `interview_scheduled`,
`interview_completed`, `offer`, `rejected`, `withdrawn`.

- Completed: `offer`, `rejected`, `withdrawn`. Active: all others.
- Pre-application: `saved`, `planning` (used for deadline reminders).
- Awaiting response: `applied`, `under_review` (used for the "pending" reminder).

### Artifact linking

A customization or interview preparation can be linked only if it belongs to the same
user **and** was generated for the same `job_id`; otherwise the request is rejected
(another user's artifact returns 404). Manual applications have no canonical job, so
generated materials cannot be linked to them. Deleting an application keeps the
generated materials.

### Summary and reminders

`GET /api/applications/summary` returns total, active, completed, upcoming deadlines
(pre-application items with a deadline within 7 days), interviews scheduled (active
item with a future interview date whose interview status is unset or `scheduled`), offers, rejected, and per-status counts.

`GET /api/applications/reminders?days=N` (default 7, range 1–60) returns, sorted by date:

| Type | Rule |
|---|---|
| `deadline` | Pre-application item whose deadline falls within the window |
| `interview` | Interview date-time within the window |
| `follow_up` | Follow-up date within the window, including overdue ones |
| `pending` | `applied` / `under_review` for ≥ 14 days with no status change and no follow-up date |

"Today" is the current UTC date; interview instants are compared in UTC and displayed in
the browser's local time zone.

### API

| Method & path | Purpose |
|---|---|
| `POST /api/applications` | Create from `job_id` (dataset) or manual fields → 201; duplicate canonical job → 409 |
| `GET /api/applications` | List with filters `status` (repeatable), `q` (company/role text), `active`, `deadline_from/to`, `applied_from/to`; `sort` = `updated_desc` (default), `created_desc`, `deadline_asc`, `applied_desc`, `company_asc` |
| `GET /api/applications/summary` | Dashboard counts |
| `GET /api/applications/reminders` | Upcoming actions |
| `GET /api/applications/{id}` | One application |
| `PATCH /api/applications/{id}` | Partial update (status, dates, interview, notes, links) |
| `DELETE /api/applications/{id}` | Delete → 204 |

All endpoints require authentication; another user's application returns 404.

### Frontend behaviour

- **Tracker page:** summary cards, search / status / active-completed filters, date-range
  filters, sort, application cards, "Upcoming actions" panel, add-manual-application form.
- **Detail page:** status change, dates, interview status and local date-time, notes,
  linked materials with open/unlink, delete.
- **Dashboard:** the same summary counts; a fresh account shows zeros and an explanatory
  empty-state message — no placeholder figures.

### Verification

Covered by `test_application_service.py`, `test_applications_api.py` and the tracker
steps in `test_m4_2_e2e_workflow.py`. Manually re-validated in M4.4 (creation from
Careers, linking, status/dates/notes persisted across reload, manual entry, reminders,
cross-user 404) — see [`FINAL_TECHNICAL_DOCUMENTATION.md`](FINAL_TECHNICAL_DOCUMENTATION.md) §22 and §25.

## M4.2 / M4.3 summary

See [`FINAL_TECHNICAL_DOCUMENTATION.md`](FINAL_TECHNICAL_DOCUMENTATION.md) §19 (M4.2
baseline and weaknesses), §20 (every M4.3 experiment with hypothesis, change, result
and decision, including the rejected ones), §24 (before/after results) and §26 (known
limitations).
