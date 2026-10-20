# Product Backlog and Feature Inventory — AI Career Companion

Part of the Agile artifact set indexed in [README.md](README.md). The same backlog, in the
Infosys template layout, is on the *Product Backlog* sheet of
[`Agile_Template_v0.1.xls`](Agile_Template_v0.1.xls).

**How this backlog was produced.** No backlog, issue tracker or sprint board was kept during
development. This backlog was reconstructed on 2026-10-17 from the source code, the API
routes, the test suites, the milestone documents in [`docs/`](../) and the Git history. It
records what exists, not what was planned at the time.

- **Priority** is a *retrospective MoSCoW label* assigned during this audit, judged from
  the project objectives in
  [`FINAL_TECHNICAL_DOCUMENTATION.md`](../FINAL_TECHNICAL_DOCUMENTATION.md) §3. No
  historical priorities were recorded.
- **Requirement IDs** (`FR-xx`, `NFR-xx`) are those of the project report,
  [`AI_Career_Companion_Project_Report.md`](../project-report/AI_Career_Companion_Project_Report.md)
  Tables 2.3 and 2.4.
- **User stories** with acceptance criteria are in [USER_STORIES.md](USER_STORIES.md); the
  links to tests are in [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md).

## Status legend

| Status | Meaning |
|---|---|
| **Done** | Implemented on `develop` and covered by automated tests that passed in the 2026-10-17 verification run ([TRACEABILITY_MATRIX.md §4](TRACEABILITY_MATRIX.md#4-verification-run-2026-10-17)). |
| **Done (feature branch)** | Implemented and tested only on `feature/ui-redesign-skill-graph`; not yet merged into `develop` or `main`. |
| **Done, partly verified** | The code exists and is unit-tested with fakes, but the real end-to-end behaviour was not evaluated. |
| **Partial** | Some of the story is implemented; the gap is stated. |
| **Not implemented** | No working feature. The application says so where a page exists. |

## 1. Feature inventory (evidence-based)

| Feature | Status | Main source files / API routes | Verification evidence | Dependencies | Known limitations |
|---|---|---|---|---|---|
| Accounts and sessions | Done | `backend/app/api/auth.py` (`/api/auth/register`, `login`, `me`, `logout`); `backend/app/services/auth.py`; `src/services/authService.ts` | `test_auth_api.py`, `test_auth_persistence.py`, `test_session_cookie.py`; e2e `auth.spec.ts`, `session-expiry.spec.ts` | SQLite, `pwdlib[argon2]` | No password reset, e-mail verification, rate limiting, CSRF tokens or OAuth (technical doc §22) |
| Career profile | Done | `backend/app/api/profile.py` (`/api/profiles`); `ProfileView` in `src/App.tsx` | `test_profile_api.py`; e2e `navigation.spec.ts` (profile saves and dashboard reflects it); unit `profileCompletion.test.ts` | Accounts | One profile per user |
| Resume upload and validation | Done | `backend/app/api/resume.py` (`POST /api/profiles/{id}/resumes`); `backend/app/services/resume_validation.py` | `test_resume_api.py`; e2e `resume-workflow.spec.ts` | Profile | PDF/DOCX only, 10 MiB |
| Resume parsing (text → sections → structured resume) | Done | `resume.py` (`extract-text`, `detect-sections`, `structure`); `pdf_extraction.py`, `docx_extraction.py`, `section_detection.py`, `structured_resume.py` (parser version 4) | `test_pdf_extraction.py`, `test_docx_extraction.py`, `test_section_detection.py`, `test_structured_resume_parser.py`, `test_resume_parser_robustness.py`, `test_resume_parser_real_world.py`, `test_resume4_regressions.py` | Upload | Rule-based; no OCR (scanned PDFs fail); unusual layouts may extract imperfectly ([RESUME_PARSING_AUDIT.md](../RESUME_PARSING_AUDIT.md)) |
| Candidate context | Done | `backend/app/api/context.py` (`/api/profiles/{id}/candidate-context`) | `test_structured_context.py`, `test_m1_m2_contract.py` | Profile, structured resume | — |
| Opportunity catalogue | Done | `backend/data/internships/career_opportunities_320.json`; `job_dataset_service.py`; `GET /api/jobs/{job_id}` | `test_job_dataset_service.py`, `test_career_opportunity_generalization.py`, `test_jobs_api.py`; `scripts/validate_job_dataset.py` | — | 320 project-authored records, 15 technology domains; not live vacancies; no deadlines or application links |
| Semantic opportunity search | Done | `GET /api/jobs/search`; `job_chunking.py`, `embedding_service.py`, `job_vector_store.py`, `job_search_service.py`, `retrieval_confidence.py`; `src/views/CareersView.tsx` | `test_job_search_service.py`, `test_job_vector_store.py`, `test_job_retrieval_integration.py`; e2e `opportunities.spec.ts` | FAISS index built locally with `scripts/build_job_vector_index.py` (gitignored) | Off-topic flag is a heuristic (11/12 off-topic queries flagged in the M4.3 evaluation) |
| Job–resume matching | Done | `GET /api/resumes/{id}/job-matches`; `job_matching.py`, `skill_relationships.py`; `JobDetailsView.tsx` | `test_job_matching.py`, `test_job_matching_api.py`, `test_job_matching_integration.py`; e2e `resume-dependent.spec.ts` | Structured resume, search | Score margins between evaluation candidates below the targets set in M4.2 (technical doc §26.2) |
| Skill-gap analysis | Done | `backend/app/api/skill_gap.py`; `skill_gap_service.py`; `SkillsView` in `src/App.tsx` | `test_skill_gap_service.py`, `test_skill_gap_evidence.py`, `test_skill_gap_api.py`; e2e `charts.spec.ts` | Structured resume, catalogue | Readiness is a deterministic weighted score, not a hiring prediction |
| Resume and cover-letter customization | Done | `backend/app/api/customization.py` (generate, list, get, edit, regenerate, export PDF/DOCX); `resume_customization_service.py`, `cover_letter_service.py`, `customization_validator.py`, `customization_export_service.py` | `test_customization_service.py`, `test_customization_validator.py`, `test_customization_quality.py`, `test_customization_api.py` | Skill gap, matching | Deterministic wording without an LLM |
| Interview preparation and mock-answer feedback | Done | `backend/app/api/interview_prep.py`; `interview_prep_service.py`, `interview_question_service.py`, `interview_mock_service.py` | `test_interview_prep_service.py`, `test_interview_prep_api.py` | Skill gap, customization | Feedback is rule-based in deterministic mode |
| Conversational career assistant | Partial | `backend/app/api/assistant.py`; `assistant_intent.py`, `assistant_context.py`, `assistant_service.py`; `AssistantView` | `test_assistant_intent.py`, `test_assistant_service.py`, `test_assistant_api.py`; M4.3 evaluation 15/16 turns | All services above | General career questions get a fixed capability message (limitation CV06, a strict `xfail` test) |
| Optional LLM rewrite layer | Done, partly verified | `backend/app/services/llm_provider.py`, `customization_llm.py`, `interview_llm.py`, `assistant_llm.py`; `LLM_PROVIDER` setting | `test_customization_llm.py` (fake provider: timeout, bad JSON, repair, fallback) | OpenAI-compatible endpoint (optional) | Live-model output quality, latency and cost were not evaluated; one manual spot check only (technical doc §26.4) |
| Application tracker | Done | `backend/app/api/applications.py` (7 endpoints); `application_service.py`; `src/components/applications/*` | `test_application_service.py`, `test_applications_api.py`, `test_m4_2_e2e_workflow.py`; e2e `opportunities.spec.ts`, `charts.spec.ts` | Accounts; optional links to customization / interview prep | Deadlines are user-entered only |
| Dashboard, Progress and derived charts | Done (feature branch: `insights.ts`, `profileCompletion.ts`, `charts.tsx`, `DashboardView.tsx` were added in `024a63d`; `develop` has the earlier in-file dashboard) | `src/views/DashboardView.tsx`, `ProgressView` in `src/App.tsx`, `src/lib/insights.ts`, `src/components/charts.tsx` | unit `insights.test.ts`, `profileCompletion.test.ts`; e2e `navigation.spec.ts`, `charts.spec.ts` | All data services | — |
| Evaluation framework and optimisation (M4.2/M4.3) | Done | `backend/app/services/m4_evaluation.py`, `backend/scripts/run_m4_evaluation.py`, `backend/data/evaluation/m4/` | `test_m4_2_evaluation_framework.py`, `test_m4_2_baseline.py`, `test_m4_3_optimizations.py` | Catalogue, index | Small synthetic evaluation set; no human-judged labels |
| Per-user data isolation | Done | `require_current_user` (`backend/app/services/auth.py`), `get_owned_profile` (`services/profile.py`), `get_owned_resume` (`services/resume.py`), used by every user-data router | Cross-user tests in every API test module; `test_m4_2_e2e_workflow.py`; e2e `session-expiry.spec.ts` | Accounts | — |
| UI redesign, accessibility and responsive layout | Done (feature branch) | `src/index.css`, `src/App.css`, `src/theme.css`, `src/components/AppNav.tsx`, `src/components/Ambient.tsx` | e2e `a11y.spec.ts`, `contrast.spec.ts`, `responsive.spec.ts`, `quality.spec.ts`, `lighting.spec.ts`, `navigation.spec.ts` | — | Branch not merged |
| Skill-graph background | Done (feature branch) | `src/components/skillGraphEngine.ts`, `src/lib/skillGraph*.ts` | unit `skillGraph.test.ts`, `skillGraphScene.test.ts`, `skillGraphSpace.test.ts`; e2e `skill-graph.spec.ts`, `skill-graph-routes.spec.ts` | Real extracted skills | Decorative only; edges are not skill relationships |
| Learning roadmap | Not implemented | `src/views/RoadmapView.tsx` shows "Not available yet" plus the current top-match gap context | e2e `roadmap-lifecycle.spec.ts`, `resume-dependent.spec.ts` (test the context panel only) | Skill gap | Legacy tables `learning_roadmaps`, `roadmap_items` are unused |
| Settings | Partial | `SettingsView` in `src/App.tsx` | e2e `navigation.spec.ts` (page opens) | — | Informational text only; no editable preferences |
| Deployment / CI | Not implemented | — | — | — | Local development project; no hosting, container or CI pipeline ([README](../../README.md)) |

## 2. Product backlog

Columns follow the request for this audit and the Infosys template. "Evidence" names the
main automated tests; the full mapping is in
[TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md).

| ID | Epic / feature | User story (short form) | User value | Priority (retro MoSCoW) | Status | Acceptance criteria | Depends on | Evidence | Known limitations |
|---|---|---|---|---|---|---|---|---|---|
| PB-01 | Accounts | As a student, I want to register, sign in and sign out so that my data is private to me. (FR-01) | Personal, persistent workspace | Must | Done | US-01 AC1–AC5 | — | `test_auth_api.py`, e2e `auth.spec.ts` | See security limitations |
| PB-02 | Accounts | As a signed-in student, I want an expired session to return me to sign-in and back to the page I was on. | No silent failures | Should | Done (feature branch for e2e) | US-02 AC1–AC3 | PB-01 | e2e `session-expiry.spec.ts` | — |
| PB-03 | Profile | As a student, I want to save my education, interests, target roles and skills. (FR-02) | Context for recommendations | Must | Done | US-03 AC1–AC4 | PB-01 | `test_profile_api.py` | — |
| PB-04 | Profile | As a student, I want to see how complete my profile is. | Know what to fill in | Could | Done (feature branch) | US-04 AC1–AC2 | PB-03 | unit `profileCompletion.test.ts` | Completion counts saved fields only |
| PB-05 | Resume | As a student, I want to upload a PDF/DOCX resume and have invalid files refused. (FR-03) | Safe, predictable input | Must | Done | US-05 AC1–AC4 | PB-03 | `test_resume_api.py`, e2e `resume-workflow.spec.ts` | 10 MiB, PDF/DOCX only |
| PB-06 | Resume | As a student, I want my resume turned into structured skills, education, experience and projects. (FR-04) | Basis for all analysis | Must | Done | US-06 AC1–AC5 | PB-05 | parser test modules (see inventory) | No OCR; heuristic parsing |
| PB-07 | Resume | As a student, I want my profile and resume combined into one candidate context. (FR-05) | One consistent input to services | Must | Done | US-07 AC1–AC2 | PB-03, PB-06 | `test_structured_context.py` | — |
| PB-08 | Discovery | As a student, I want to search opportunities in plain language. (FR-06) | Find relevant openings | Must | Done | US-08 AC1–AC4 | Index build | `test_job_search_service.py`, `test_jobs_api.py`, e2e `opportunities.spec.ts` | Heuristic off-topic flag |
| PB-09 | Matching | As a student, I want ranked matches with a score and the matched and missing skills. (FR-07) | Know which openings fit | Must | Done | US-09 AC1–AC4 | PB-06, PB-08 | `test_job_matching*.py` | Margins below M4.2 targets |
| PB-10 | Skill gap | As a student, I want a requirement-by-requirement gap analysis for a chosen opportunity. (FR-08) | Know what to learn | Must | Done | US-10 AC1–AC5 | PB-06, PB-08 | `test_skill_gap_*.py`, e2e `charts.spec.ts` | — |
| PB-11 | Customization | As a student, I want a tailored summary and cover letter that never claims skills I lack, and to edit and export it. (FR-09, NFR-01) | Faster, honest applications | Should | Done | US-11 AC1–AC6 | PB-10 | `test_customization_*.py` | — |
| PB-12 | Interview prep | As a student, I want interview questions tied to my projects and gaps, and feedback on a practice answer. (FR-10) | Targeted preparation | Should | Done | US-12 AC1–AC4 | PB-10 | `test_interview_prep_*.py` | Rule-based feedback |
| PB-13 | Assistant | As a student, I want to ask follow-up questions in a chat that remembers my resume and selected job. (FR-11) | Guided navigation of results | Should | Partial | US-13 AC1–AC5 (AC5 not met) | PB-09 – PB-12 | `test_assistant_*.py`, `test_m4_2_baseline.py` | CV06 |
| PB-14 | Tracker | As a student, I want to track applications with statuses, dates, notes and linked materials. (FR-12) | One place for applications | Must | Done | US-14 AC1–AC6 | PB-01; optional PB-11, PB-12 | `test_application*.py` | User-entered dates only |
| PB-15 | Tracker | As a student, I want summary counts and reminders for deadlines, interviews and follow-ups. (FR-12) | Do not miss dates | Should | Done | US-15 AC1–AC3 | PB-14 | `test_application_service.py` | Date rules in UTC |
| PB-16 | Dashboard | As a student, I want an overview that shows only real data and honest empty states. (NFR-06) | Trustworthy summary | Must | Done (tests on feature branch) | US-16 AC1–AC3 | PB-06, PB-09, PB-14 | unit `insights.test.ts`, e2e `navigation.spec.ts`, `charts.spec.ts` | — |
| PB-17 | Optional LLM | As a student, I want better wording when an LLM is configured, without losing grounding. (NFR-05) | Readability | Could | Done, partly verified | US-17 AC1–AC4 | PB-11, PB-12, PB-13 | `test_customization_llm.py` | Live model not evaluated |
| PB-18 | Isolation | As a student, I want no other user to see or change my data. (NFR-03) | Privacy | Must | Done | US-18 AC1–AC3 | PB-01 | cross-user tests; `test_m4_2_e2e_workflow.py` | Local security scope |
| PB-19 | Quality | As the developer, I want an offline evaluation with a frozen baseline so improvements are measured. | Evidence-based changes | Should | Done | US-19 AC1–AC3 | PB-08 – PB-13 | `test_m4_2_*.py`, `test_m4_3_optimizations.py` | Small synthetic set |
| PB-20 | UI quality | As a student using a keyboard, screen reader or phone, I want every page usable and readable. | Accessibility | Should | Done (feature branch) | US-20 AC1–AC4 | — | e2e `a11y`, `contrast`, `responsive`, `quality` specs | Not merged into `develop` |
| PB-21 | Visual design | As a student, I want a background that reflects my real skills without getting in the way. | Engagement | Won't (for this release's core scope; built anyway) | Done (feature branch) | US-21 AC1–AC3 | PB-06 | unit/e2e skill-graph tests | Decorative |
| PB-22 | Learning roadmap | As a student, I want a generated learning roadmap from my skill gaps. | Learning plan | Could | Not implemented | — (page states it is unavailable) | PB-10 | e2e `roadmap-lifecycle.spec.ts` covers only the context panel | Future enhancement |
| PB-23 | Settings | As a student, I want to change workspace preferences. | Personalisation | Won't (this release) | Partial (informational page) | — | — | — | No editable settings |
| PB-24 | Deployment | As a mentor, I want to open a hosted version. | Easy review | Won't (this release) | Not implemented | — | — | — | Local only |
| PB-25 | Hardening | As an operator, I want HTTPS, CSRF protection, rate limiting and password reset. | Production safety | Won't (this release) | Not implemented (Secure cookie outside development is implemented) | — | PB-24 | `test_session_cookie.py` covers only the cookie flag | Technical doc §22, §27 |
