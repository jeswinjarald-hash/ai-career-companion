# User Stories and Acceptance Criteria — AI Career Companion

Part of the Agile artifact set indexed in [README.md](README.md). Each story refines one
backlog item in [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md).

**Source of these stories.** They were written on 2026-10-17 from the behaviour that the code
and its automated tests actually implement. They were not written before development; no
story cards from the development period exist. Acceptance criteria describe implemented
behaviour and name the test that checks it. Whether those tests passed in the latest run is
recorded in [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md), not here.

**Persona.** *Student*: a student or recent graduate looking for an internship, entry-level,
graduate, trainee or apprenticeship role in technology. This is the only user role in the
application (project report §3, "User Roles and Access Restrictions").

**Verification methods.** *API test* = pytest with FastAPI `TestClient` in `backend/tests/`;
*service test* = pytest on a service module; *unit test* = `tests/unit/*.test.ts`;
*e2e* = Playwright spec in `e2e/` against an isolated backend and database; *evaluation* =
the offline M4 evaluation in `backend/data/evaluation/m4/`.

---

## US-01 Register, sign in and sign out (PB-01, FR-01) — Done

*As a student, I want to create an account and sign in and out, so that my profile, resume
and applications are kept private to me.*

Precondition: the backend is running; the e-mail address is not registered.

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a new e-mail and matching passwords **when** I register **then** one user and exactly one linked career profile are created. | API test `test_auth_api::test_register_creates_user_and_one_linked_profile` |
| AC2 | **Given** mismatched passwords or an e-mail that already exists **when** I register **then** the request is rejected. | `test_auth_api::test_register_rejects_mismatched_passwords_and_duplicate_email` |
| AC3 | **Given** correct credentials **when** I sign in **then** an `HttpOnly` session cookie is set; **given** wrong credentials **then** sign-in fails. | `test_auth_api::test_login_succeeds_and_invalid_login_fails`, `test_session_cookie.py` |
| AC4 | **Given** I am signed in **when** I sign out **then** the session is deleted and `GET /api/auth/me` returns 401. | `test_auth_api::test_logout_invalidates_session` |
| AC5 | **Given** I am signed out **when** I open the app **then** I see the sign-in screen and cannot reach account pages. | e2e `auth.spec.ts` |

Edge cases covered: duplicate e-mail, mismatched password, repeated `/me` calls
(`test_me_requires_session_and_survives_repeated_requests`).
Not covered (not implemented): password reset, e-mail verification, login throttling.

## US-02 Recover from an expired session (PB-02) — Done (e2e on feature branch)

*As a signed-in student, I want an expired session to send me back to sign-in and then to the
page I was on, so that I do not lose my place.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** an expired session on a job-scoped page **when** I sign in again **then** the same opportunity is selected. | e2e `session-expiry.spec.ts` "signing in again after expiry restores the selected job" |
| AC2 | **Given** an expired session on an application page **when** I sign in again **then** the same application opens. | same spec, "…restores the selected application" |
| AC3 | **Given** a *different* user signs in on that URL **then** they still cannot see the first user's application. | same spec, "a different user signing in on that URL still cannot see the application" |

## US-03 Maintain a career profile (PB-03, FR-02) — Done

*As a student, I want to save my education, degree, experience level, interests, target roles,
skills and goals, so that recommendations reflect what I am looking for.*

Precondition: signed in (the profile is created at registration).

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** my profile **when** I update and save fields **then** they persist and are returned on reload. | `test_profile_api::test_registration_creates_linked_profile_and_update_persists`; e2e `navigation.spec.ts` "the profile form saves real data and the dashboard reflects it" |
| AC2 | **Given** I am not signed in **when** I call a profile route **then** I get 401. | `test_profile_api::test_profile_routes_require_authentication` |
| AC3 | **Given** another user's profile ID **when** I read or update it **then** I get 404. | `test_profile_api::test_user_cannot_access_or_update_another_users_profile` |
| AC4 | **Given** an invalid payload **then** it is rejected with a validation error. | `test_profile_api::test_create_profile_requires_auth_and_validates_payload` |

## US-04 See profile completion (PB-04) — Done (feature branch)

*As a student, I want to see how much of my profile is filled in, so that I know what is
missing.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a saved profile **when** I open Progress **then** completion is computed only from saved fields ("N of M profile details saved"). | unit `profileCompletion.test.ts` |
| AC2 | **Given** the profile is not loaded **then** completion shows "N/A", never 0 %. | `ProgressView` in `src/App.tsx`; unit `profileCompletion.test.ts` |

## US-05 Upload a resume safely (PB-05, FR-03) — Done

*As a student, I want to upload my PDF or DOCX resume and have invalid files refused, so that
only a usable document is analysed.*

Precondition: signed in with a profile.

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a valid PDF or DOCX ≤ 10 MiB **when** I upload it **then** it is stored under a generated name and its metadata is returned. | `test_resume_api::test_uploads_pdf_and_docx_and_persists_metadata` |
| AC2 | **Given** an empty, unsupported, corrupt, mismatched or oversized file **then** it is rejected with HTTP 400 and nothing is stored. | `test_resume_api::test_rejects_mismatched_corrupt_and_oversized_uploads_without_persistence`, `…rejects_missing_profile_empty_and_unsupported_files` |
| AC3 | **Given** a file whose content is not really a PDF **then** the server rejects it and my previous active resume stays active. | e2e `resume-workflow.spec.ts` |
| AC4 | **Given** another user's profile **when** I upload to it **then** I get 404. | `test_resume_api::test_user_cannot_access_or_upload_to_another_users_profile_or_resume` |

## US-06 Turn a resume into structured data (PB-06, FR-04) — Done

*As a student, I want my resume converted into skills, education, experience, projects,
certifications and languages, so that later analysis uses my real evidence.*

Precondition: an uploaded resume.

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** an uploaded resume **when** I click *Process resume* **then** extraction → sections → structure → candidate context run in order and the results page shows the extracted data. | e2e `resume-workflow.spec.ts` "uploading a synthetic resume produces real results…" |
| AC2 | **Given** a word-fragmented (Google Docs/Skia) PDF **then** text is rebuilt in reading order. | `test_pdf_extraction.py` (with `skia_pdf_fixture.py`) |
| AC3 | **Given** a DOCX with text boxes and headers **then** their text is included. | `test_docx_extraction.py` |
| AC4 | **Given** unusual layouts **then** fragments are not reported as projects, and suspicious output carries `parser_warnings`. | `test_resume_parser_robustness.py`, `test_resume_parser_real_world.py`, `test_resume4_regressions.py` |
| AC5 | **Given** an analysis failure **then** it is explained and can be retried. | e2e `resume-workflow.spec.ts` "an analysis failure is explained and can be retried from Overview" |

Known limitation: image-only PDFs fail explicitly (no OCR).

## US-07 Build the candidate context (PB-07, FR-05) — Done

*As a student, I want my profile and structured resume combined, so that every service works
from the same facts.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a structured resume **when** context is generated **then** it is persisted, and regenerating it updates rather than duplicates it. | `test_structured_context::test_structured_resume_and_candidate_context_are_persisted_and_idempotent` |
| AC2 | **Given** earlier stages have not run **then** structuring/context generation is refused. | `test_structured_context::test_structure_and_context_require_previous_stages` |

## US-08 Search opportunities (PB-08, FR-06) — Done

*As a student, I want to describe what I am looking for in plain words, so that I see relevant
opportunities from the catalogue.*

Precondition: the FAISS index has been built locally.

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a query and `top_k` between 1 and 20 **then** unique, ranked opportunities are returned; out-of-range values are rejected. | `test_jobs_api::test_job_search_validates_query_and_top_k`, `test_job_search_service::test_search_aggregates_chunks_into_unique_jobs` |
| AC2 | **Given** an off-topic query **then** results carry `query_confidence = unsupported_area` and the page shows a notice; results are not hidden. | `test_m4_3_optimizations::test_flagged_searches_still_return_results`, `…::test_off_topic_held_out_queries_are_flagged`; evaluation (11/12 off-topic flagged) |
| AC3 | **Given** no results or a search error **then** an empty state or an error with recovery is shown. | e2e `opportunities.spec.ts` |
| AC4 | **Given** an opportunity ID **then** its real catalogue record is shown; an unknown ID returns 404. | `test_jobs_api::test_job_details_returns_real_dataset_record`, `…unknown_id_is_404` |

## US-09 See ranked job matches (PB-09, FR-07) — Done

*As a student, I want opportunities ranked by an explainable match score, so that I know which
ones fit me and why.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a structured resume **then** matches are ordered by `match_score`, not retrieval order. | `test_job_matching::test_matching_service_ranks_by_match_score_not_retrieval_order` |
| AC2 | **Then** each match lists matched and missing required/preferred skills and reasoning. | `test_job_matching_api::test_job_matches_endpoint_uses_structured_resume_and_validates_state` |
| AC3 | **Given** a related technology for a *preferred* skill **then** it earns half credit; required skills need direct evidence. | `test_m4_3_optimizations::test_related_skills_earn_partial_preferred_credit_but_are_never_reported_as_matched`, `…::test_required_skills_still_need_direct_evidence` (E3e) |
| AC4 | **Given** a job details page **then** the shown match score equals the API value. | e2e `resume-dependent.spec.ts` "Defect C: match score on job details" |

## US-10 Analyse the skill gap for one opportunity (PB-10, FR-08) — Done

*As a student, I want each requirement of a chosen opportunity marked as matched, partial or
missing with evidence, so that I know exactly what to improve.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a resume and an opportunity **then** every requirement is classified with quoted evidence and a recommendation, and the result is persisted. | `test_skill_gap_api::test_full_pipeline_produces_grounded_real_data_analysis_and_persists` |
| AC2 | **Given** a missing *preferred* skill **then** it is never a critical gap. | `test_skill_gap_service::test_preferred_missing_skill_never_lands_in_critical_gaps` |
| AC3 | **Given** the same inputs twice **then** readiness is identical. | `test_skill_gap_service::test_determinism_same_inputs_produce_identical_score` |
| AC4 | **Given** a skill only in my profile **then** it is labelled self-reported with lower confidence. | `test_m4_3_optimizations::test_profile_only_skill_counts_but_is_described_as_self_reported` (E7) |
| AC5 | **Then** the readiness chart matches the backend breakdown row by row. | e2e `charts.spec.ts` |

Edge cases: unknown resume or job → 404; another user's resume → 404
(`test_skill_gap_api.py`).

## US-11 Tailor resume summary and cover letter (PB-11, FR-09, NFR-01) — Done

*As a student, I want a tailored summary, skill order, project ranking and cover letter that
only use my real evidence, and to edit and export them, so that I can apply faster without
making false claims.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a sentence with an invented metric, unsupported skill, leadership claim or years of experience **then** the validator removes it. | `test_customization_validator::test_fabricated_metric_is_rejected` and the rest of that module |
| AC2 | **Then** the result states whether the grounding check passed and whether it is "Grounded Fallback" or LLM-assisted. | `test_customization_service.py`, `test_customization_quality.py` |
| AC3 | **Given** I generate again or regenerate **then** a new version is created and earlier versions are kept. | `test_customization_api::test_regenerate_creates_a_new_version_and_keeps_the_prior_one` |
| AC4 | **Given** I edit the text **then** my edit is saved and marked as user-edited. | `test_customization_api::test_user_edit_is_persisted_and_marked_as_user_edited_not_generated` |
| AC5 | **Given** I export **then** I receive PDF or DOCX; an invalid format is rejected. | `test_customization_api::test_export_returns_pdf_and_docx_for_resume_and_cover_letter`, `…rejects_invalid_document_or_format` |
| AC6 | **Given** another user's customization **then** I get 404. | `test_customization_api::test_user_cannot_access_or_edit_another_users_customization` |

## US-12 Prepare for an interview (PB-12, FR-10) — Done

*As a student, I want interview questions based on my projects, the job and my gaps, and
feedback on a practice answer, so that my preparation is targeted.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Then** questions are produced in six categories (technical, resume, project, role, HR, skill-gap) with difficulty and source. | `test_interview_prep_api::test_full_preparation_structure_and_categories` |
| AC2 | **Given** a practice answer **then** structured feedback (strengths, improvements, missing points, structure) is returned. | `test_interview_prep_api::test_mock_answer_endpoint_returns_grounded_evaluation` |
| AC3 | **Given** an out-of-range question index **then** the request is rejected. | `test_interview_prep_api::test_mock_answer_rejects_out_of_range_question_index` |
| AC4 | **Given** regeneration **then** a new version is created and the previous one kept. | `test_interview_prep_api::test_regenerate_creates_a_new_version_and_keeps_the_prior_one` |

## US-13 Ask the career assistant (PB-13, FR-11) — Partial

*As a student, I want to ask follow-up questions in a chat that keeps my resume and selected
opportunity in context, so that I can explore my results conversationally.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a message **then** it is routed to the matching, skill-gap, customization or interview service; the assistant does not compute its own scores. | `test_assistant_intent.py`, `test_assistant_service.py` |
| AC2 | **Given** follow-up turns **then** the active resume and job are kept; switching jobs does not leak the previous job. | `test_assistant_service.py`; evaluation conversations |
| AC3 | **Given** "find internships in <area>" **then** results come from the requested area and are scored against my resume. | `test_m4_3_optimizations::test_discovery_retrieves_the_requested_area_and_scores_against_the_resume` (E1); evaluation discovery 3/3 |
| AC4 | **Then** conversations can be created, listed, reopened in order and deleted, and another user's conversation returns 404. | `test_assistant_api.py` |
| AC5 | **Given** a general career question (e.g. salary negotiation) **then** a substantive answer is given. | **Not met.** Strict `xfail` `test_m4_2_baseline::test_general_career_question_gets_a_substantive_answer` (CV06) |

## US-14 Track applications (PB-14, FR-12) — Done

*As a student, I want to track opportunities and external applications with status, my own
dates, notes and linked materials, so that I manage all applications in one place.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a catalogue opportunity **when** I track it **then** company, title, type, location and description are copied server-side; client-supplied details are refused. | `test_applications_api::test_dataset_application_snapshots_the_canonical_opportunity`, `…rejects_client_supplied_opportunity_details` |
| AC2 | **Given** I track the same opportunity twice **then** I get 409; manual look-alikes are allowed. | `test_applications_api::test_duplicate_dataset_application_is_rejected_but_manual_lookalikes_are_allowed` |
| AC3 | **Given** a catalogue opportunity **then** no deadline is invented. | `test_applications_api::test_dataset_application_never_derives_a_deadline` |
| AC4 | **Given** a status change **then** `status_updated_at` is updated; invalid statuses are rejected. | `test_applications_api::test_status_updates_track_status_updated_at_and_allow_moving_backward`, `…invalid_or_cleared_status_is_rejected` |
| AC5 | **Given** materials for the same job **then** they can be linked; materials for another job or user cannot. | `test_application_service.py`, `test_m4_2_e2e_workflow.py` |
| AC6 | **Given** another user's application **then** read, update and delete return 404. | `test_applications_api::test_user_cannot_read_update_or_delete_another_users_application` |

## US-15 See tracker summary and reminders (PB-15, FR-12) — Done

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** applications **then** the summary returns total, active, completed, upcoming deadlines, interviews, offers, rejected and per-status counts. | `test_application_service.py` |
| AC2 | **Given** `days=N` (1–60) **then** reminders list deadlines, interviews, follow-ups and applications pending ≥ 14 days, sorted by date. | `test_application_service.py` |
| AC3 | **Given** no applications **then** the status chart is absent; with applications it is exact. | e2e `charts.spec.ts` |

## US-16 Trust the overview (PB-16, NFR-06) — Done (tests on feature branch)

*As a student, I want the overview to show only real data, so that I can trust it.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** a new account **then** the overview says no resume is analysed and shows zero tracker counts — no placeholder figures. | e2e `navigation.spec.ts` "empty states without a resume are honest" |
| AC2 | **Then** every derived value comes from `src/lib/insights.ts` or an API field; unavailable values show "Not available", never 0. | unit `insights.test.ts` |
| AC3 | **Given** a load error **then** it is shown with *Try again*, which recovers. | e2e `resume-workflow.spec.ts` (Overview error tests) |

## US-17 Optional LLM wording (PB-17, NFR-05) — Done, partly verified

*As a student, I want clearer wording when an LLM is configured, without losing grounding.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** `LLM_PROVIDER=none` **then** no external call is made and results are deterministic. | `tests/conftest.py` guard; `test_isolation.py` |
| AC2 | **Given** the provider times out **then** the deterministic result is used without a repair attempt. | `test_customization_llm::test_provider_timeout_falls_back_without_a_repair_attempt` |
| AC3 | **Given** malformed JSON **then** one repair is attempted, then fallback. | `test_customization_llm::test_malformed_json_shape_triggers_repair_then_fallback` |
| AC4 | **Given** a live model **then** output quality, grounding and latency are acceptable. | **Not verified.** No live-model evaluation was performed (technical doc §26.4). |

## US-18 Keep my data private (PB-18, NFR-03) — Done

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** no session **then** every user-data route returns 401. | `*_requires_authentication` tests in each API module |
| AC2 | **Given** another user's object **then** the API returns 404 (not 403). | cross-user tests in each API module |
| AC3 | **Given** a full workflow by user A **then** user B cannot read or link any of it. | `test_m4_2_e2e_workflow::test_complete_student_workflow_from_profile_to_application_tracking` |

## US-19 Measure changes against a frozen baseline (PB-19) — Done

*As the developer, I want an offline evaluation with a frozen baseline, so that every
optimisation is accepted or rejected on measured results.*

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** the evaluation runs **then** it is offline and forces `LLM_PROVIDER=none`. | `backend/data/evaluation/m4/README.md`; `test_m4_2_evaluation_framework.py` |
| AC2 | **Then** every retrieval label is re-derived from its rule, so a silent dataset change fails the suite. | `test_m4_2_evaluation_framework.py` |
| AC3 | **Then** known weaknesses are encoded as strict `xfail`s and regression floors. | `test_m4_2_baseline.py` (1 strict `xfail` remaining) |

## US-20 Use every page with keyboard, screen reader or phone (PB-20) — Done (feature branch)

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Then** sign-in, new-user and analysed-resume screens have no axe WCAG A/AA violations. | e2e `a11y.spec.ts` |
| AC2 | **Then** visible text meets WCAG AA contrast on the rendered theme. | e2e `contrast.spec.ts` |
| AC3 | **Then** every screen fits every tested width without horizontal overflow. | e2e `responsive.spec.ts` |
| AC4 | **Given** reduced-motion preference **then** entry animations and transitions are off; focus is visible. | e2e `quality.spec.ts` |

## US-21 Background reflects my real skills (PB-21) — Done (feature branch)

| AC | Given / When / Then | Verification |
|---|---|---|
| AC1 | **Given** no resume **then** no skills are drawn; **given** an analysed resume **then** exactly its skills are drawn. | e2e `skill-graph.spec.ts` |
| AC2 | **Given** sign-out **then** the graph is cleared and the next user never sees previous skills. | e2e `skill-graph-routes.spec.ts` |
| AC3 | **Then** decorative layers never intercept input, and reduced motion gives a static composition. | e2e `quality.spec.ts`, `skill-graph.spec.ts` |

## Stories not implemented

| Backlog | Story | Status |
|---|---|---|
| PB-22 | Generated learning roadmap | Not implemented. `RoadmapView` states "Not available yet". |
| PB-23 | Editable settings | Settings page is informational only. |
| PB-24 | Hosted deployment | Not implemented. |
| PB-25 | Production hardening (CSRF tokens, rate limiting, password reset, HTTPS) | Not implemented; only the `Secure` cookie flag outside development exists. |
