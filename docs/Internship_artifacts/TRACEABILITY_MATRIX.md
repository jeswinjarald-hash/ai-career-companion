# Requirements Traceability Matrix — AI Career Companion

Part of the Agile artifact set indexed in [README.md](README.md).

Chain: **Requirement → Backlog item → User story / acceptance criteria → Implementation →
Verification → Status.** Requirement IDs (`FR-xx`, `NFR-xx`), use-case IDs (`UC-xx`) and
test-case IDs `TC-01` – `TC-16` come from the project report
([`AI_Career_Companion_Project_Report.md`](../project-report/AI_Career_Companion_Project_Report.md),
Tables 2.3, 2.4, 3.5, 7.2 and 7.3). Test cases `TC-17` – `TC-30` were added in this audit and
are listed in [`Unit_Test_Plan_v0.1.xlsx`](Unit_Test_Plan_v0.1.xlsx). All test paths are
real files. Backend tests are in `backend/tests/`.

Status values: see the legend in [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md#status-legend).
"Verified 2026-10-17" means the named tests passed in the run recorded in §4.

## 1. Functional requirements

| Req | Use case | Backlog | Story / AC | Implementation (backend → frontend) | Verification (automated) | Test cases | Status |
|---|---|---|---|---|---|---|---|
| FR-01 Register, sign in, current user, sign out | UC-01 | PB-01, PB-02 | US-01 AC1–5; US-02 AC1–3 | `api/auth.py`, `services/auth.py` → `src/services/authService.ts`, `App.tsx` | `test_auth_api.py`, `test_auth_persistence.py`, `test_session_cookie.py`, `test_cors.py`; e2e `auth.spec.ts`, `session-expiry.spec.ts` | TC-01, TC-02, TC-15, TC-22 | Done — verified 2026-10-17 |
| FR-02 One profile per user, updatable | UC-01 | PB-03, PB-04 | US-03 AC1–4; US-04 AC1–2 | `api/profile.py`, `services/profile.py` → `profileService.ts`, `ProfileView`, `src/lib/profileCompletion.ts` | `test_profile_api.py`; unit `profileCompletion.test.ts`; e2e `navigation.spec.ts` | TC-01, TC-19 | Done — PB-04 on feature branch |
| FR-03 Accept PDF/DOCX ≤ 10 MiB, reject others | UC-02 | PB-05 | US-05 AC1–4 | `api/resume.py`, `services/resume_validation.py` → `resumeService.ts`, Resume Studio | `test_resume_api.py`; e2e `resume-workflow.spec.ts` | TC-03, TC-04, TC-21 | Done — verified 2026-10-17 |
| FR-04 Extract text, detect sections, structure | UC-02 | PB-06 | US-06 AC1–5 | `pdf_extraction.py`, `docx_extraction.py`, `text_utils.py`, `section_detection.py`, `structured_resume.py` | `test_pdf_extraction.py`, `test_docx_extraction.py`, `test_section_detection.py`, `test_structured_resume_parser.py`, `test_resume_parser_robustness.py`, `test_resume_parser_real_world.py`, `test_resume4_regressions.py`, `test_video_audit_regressions.py`; e2e `resume-workflow.spec.ts` | TC-21 | Done — verified 2026-10-17 (no OCR) |
| FR-05 Persisted candidate context | UC-02 | PB-07 | US-07 AC1–2 | `api/context.py`, `services/candidate_context.py` | `test_structured_context.py`, `test_m1_m2_contract.py` | — | Done — verified 2026-10-17 |
| FR-06 Semantic search, 1–20 results | UC-04 | PB-08 | US-08 AC1–4 | `api/jobs.py`, `job_chunking.py`, `embedding_service.py`, `job_vector_store.py`, `job_search_service.py`, `retrieval_confidence.py` → `jobService.ts`, `CareersView.tsx` | `test_jobs_api.py`, `test_job_search_service.py`, `test_job_vector_store.py`, `test_job_retrieval_integration.py`, `test_m4_3_optimizations.py`; e2e `opportunities.spec.ts`, `resume-dependent.spec.ts` (Defect B) | TC-05 | Done — verified 2026-10-17 |
| FR-07 Explainable match ranking | UC-03 | PB-09 | US-09 AC1–4 | `resume.py` (`/job-matches`), `job_matching.py`, `skill_relationships.py`, `education_assessment.py` → `CareersView.tsx`, `JobDetailsView.tsx` | `test_job_matching.py`, `test_job_matching_api.py`, `test_job_matching_integration.py`; e2e `resume-dependent.spec.ts` (Defect C) | TC-06 | Done — verified 2026-10-17 |
| FR-08 Skill-gap analysis | UC-05 | PB-10 | US-10 AC1–5 | `api/skill_gap.py`, `skill_gap_service.py`, `skill_gap_evidence.py` → `skillGapService.ts`, `SkillsView` | `test_skill_gap_service.py`, `test_skill_gap_evidence.py`, `test_skill_gap_api.py`; e2e `charts.spec.ts` | TC-07, TC-08, TC-26 | Done — verified 2026-10-17 |
| FR-09 Generate, edit, version, export summary + cover letter | UC-06 | PB-11 | US-11 AC1–6 | `api/customization.py`, `resume_customization_service.py`, `cover_letter_service.py`, `customization_validator.py`, `customization_export_service.py` → `customizationService.ts`, `CustomizeView` | `test_customization_service.py`, `test_customization_validator.py`, `test_customization_quality.py`, `test_customization_api.py` | TC-09 | Done — verified 2026-10-17 (no dedicated e2e spec) |
| FR-10 Interview prep + practice feedback | UC-07 | PB-12 | US-12 AC1–4 | `api/interview_prep.py`, `interview_prep_service.py`, `interview_question_service.py`, `interview_mock_service.py` → `interviewPrepService.ts`, `InterviewPrepView` | `test_interview_prep_service.py`, `test_interview_prep_api.py` | — | Done — verified 2026-10-17 (no dedicated e2e spec) |
| FR-11 Assistant reusing the services | UC-08 | PB-13 | US-13 AC1–5 | `api/assistant.py`, `assistant_intent.py`, `assistant_context.py`, `assistant_handlers.py`, `assistant_service.py` → `assistantService.ts`, `AssistantView` | `test_assistant_intent.py`, `test_assistant_service.py`, `test_assistant_api.py`, `test_m4_3_optimizations.py`; strict `xfail` CV06 | TC-16 | **Partial** — AC5 fails (expected `xfail`) |
| FR-12 Track applications, dates, notes, links, reminders | UC-09 | PB-14, PB-15 | US-14 AC1–6; US-15 AC1–3 | `api/applications.py`, `application_service.py` → `applicationService.ts`, `src/components/applications/*` | `test_application_service.py`, `test_applications_api.py`, `test_m4_2_e2e_workflow.py`; e2e `opportunities.spec.ts`, `charts.spec.ts` | TC-12, TC-13, TC-14, TC-26 | Done — verified 2026-10-17 |

## 2. Non-functional requirements

| Req | Backlog / story | Implementation | Verification | Test cases | Status |
|---|---|---|---|---|---|
| NFR-01 Grounding | PB-11 / US-11 AC1–2 | `customization_validator.py` (`check_unsupported_claims`), `is_reliable_project` | `test_customization_validator.py`; offline evaluation fault injection (10/10 at M4.3) | TC-09, TC-29 | Done. Fresh evaluation on 2026-10-17: 0 violations, but see §5 D1 |
| NFR-02 Explainability | PB-09, PB-10 | matched/missing items and reasoning in `job_matching.py`, `skill_gap_service.py` | `test_job_matching_api.py`, `test_skill_gap_api.py` | TC-06, TC-07 | Done |
| NFR-03 Privacy / isolation | PB-18 / US-18 | `require_current_user`, `get_owned_profile`, `get_owned_resume`; 404 for foreign objects | cross-user tests in every API module; `test_m4_2_e2e_workflow.py`; e2e `session-expiry.spec.ts` | TC-04, TC-14, TC-22 | Done — verified 2026-10-17 |
| NFR-04 Determinism with `LLM_PROVIDER=none` | PB-17 / US-17 AC1 | deterministic services; `NullLLMProvider` | `test_skill_gap_service::test_determinism_same_inputs_produce_identical_score`; `test_isolation.py` | TC-08, TC-25 | Done |
| NFR-05 LLM failure → fallback | PB-17 / US-17 AC2–4 | `llm_provider.py`, `customization_llm.py`, `interview_llm.py`, `assistant_llm.py` | `test_customization_llm.py` (fake providers) | TC-10, TC-11 | Done for fallback; live model **not verified** |
| NFR-06 No fabricated display values | PB-16 / US-16 | `src/lib/insights.ts`, empty states, `RoadmapView` "Not available yet" | unit `insights.test.ts`; e2e `navigation.spec.ts`, `charts.spec.ts`, `skill-graph.spec.ts` | TC-18, TC-26, TC-27, TC-28 | Done (tests on feature branch); TC-27 failed intermittently on 2026-10-17 (see §4) |
| NFR-07 Maintainability (services + tests) | PB-19 | service modules; API types check | `npm run api:check`; `npx tsc -b`; `npm run lint` | — | Done — verified 2026-10-17 |
| NFR-08 Responsiveness of deterministic operations | — | in-process caches (M4.3 E10) | Timings in technical doc §23 (single development machine, M4.3) | — | Measured once; not re-measured |
| Accessibility (not in the report's NFR table) | PB-20 / US-20 | design tokens, focus styles, skip link, ARIA | e2e `a11y.spec.ts`, `contrast.spec.ts`, `responsive.spec.ts`, `quality.spec.ts` | TC-23, TC-24 | Done (feature branch) |

## 3. Requirements with no implementation

| Backlog | Requirement | Status | Note |
|---|---|---|---|
| PB-22 | Learning-roadmap generation | Not implemented | Only the gap-context panel is tested (`roadmap-lifecycle.spec.ts`) |
| PB-23 | Editable settings | Partial | Informational page; no test of preferences because none exist |
| PB-24 | Hosted deployment | Not implemented | — |
| PB-25 | Production hardening | Not implemented, except the Secure cookie (`test_session_cookie.py`) | — |

## 4. Verification run 2026-10-17

Checked on the working tree of `feature/ui-redesign-skill-graph` at `cd30486`, which
contains all of `develop`. The only changes in the working tree were untracked documentation.
Commands as in [DEFINITION_OF_DONE.md §2](DEFINITION_OF_DONE.md#2-release-level-definition-of-done-all-gates).

| Gate | Result |
|---|---|
| Backend `pytest -q` | **555 passed, 1 xfailed** (CV06), 2 third-party deprecation warnings, 47.72 s |
| Frontend unit `npm run test:unit` | **80 passed** (9.5 s) |
| `npx tsc -b` | exit 0 |
| `npm run lint` | exit 0, no problems reported |
| `npm run api:check` | API types match the backend schema |
| Build `npx vite build --outDir <scratch> --emptyOutDir` | succeeded; JS 396.87 kB (116.46 kB gzip), CSS 58.90 kB (11.87 kB gzip) |
| `scripts/validate_job_dataset.py` | `"status": "PASS"` |
| `scripts/run_m4_evaluation.py --output-dir <scratch>` | completed; differs from the tracked results — see §5 D1 |
| Browser `npm run test:e2e` | **96 passed, 1 failed** (14.3 min). Failure: `navigation.spec.ts` "empty states without a resume are honest". All of its assertions passed, but the network guard recorded `requestfailed: GET http://localhost:8100/api/profiles/20/resumes net::ERR_ABORTED`. Re-running only that test 5 times (`--repeat-each=5`): **5 passed**. The failure is **intermittent and not fixed** (an in-flight request aborted by a page navigation, which the guard does not exempt). |

**Follow-up run after the D1/D2 fixes (2026-10-17, same branch, with the three uncommitted
code changes listed in [README §4.3](README.md#43-files-changed-in-this-audit)):**

| Gate | Result |
|---|---|
| Targeted: `pytest -q tests/test_m4_2_evaluation_framework.py tests/test_m4_2_baseline.py tests/test_m4_3_optimizations.py` | 122 passed, 1 xfailed |
| Targeted: `npm run test:e2e -- e2e/navigation.spec.ts --repeat-each=10` | 70 passed |
| Backend `pytest -q` | **556 passed, 1 xfailed** (CV06), 2 warnings, 41.53 s |
| Frontend unit `npm run test:unit` | **80 passed** |
| `npx tsc -b` / `npm run lint` / `npm run api:check` | exit 0 / exit 0 / types match |
| Build to a scratch directory | succeeded |
| `scripts/validate_job_dataset.py` | PASS |
| `scripts/run_m4_evaluation.py --output-dir <scratch>` | 0 violations; differences explained in §5.1 |
| Browser `npm run test:e2e` | **97 passed, 0 failed** (14.2 min), including all 7 `guard.spec.ts` checks |

Not run on 2026-10-17: the manual demo workflow (technical doc §25; last run 2026-10-05) and
any live-LLM check.

## 5. Discrepancies found during verification

| ID | Finding | Evidence | Recommended action |
|---|---|---|---|
| D1 | The tracked M4.3 evaluation results no longer matched a fresh run of the same evaluation on the current code. Unchanged: retrieval metrics, matching, M2 profiles, consistency, hand-off, conversation outcomes, and **0 grounding violations**. Changed: 892 structured checks instead of 926; 1 needs-human-review item instead of 0; `customization_validation_passed` / `interview_validation_passed` false for all 16 flags (the tracked file had 15 true, 1 false); interview question counts and three assistant answer previews. | `backend/data/evaluation/m4/results/m4_3_optimized_results.json` vs scratch runs | See §5.1 — investigated and partly fixed. |
| D2 | Intermittent e2e failure (§4). | §4 | See §5.2 — root cause reproduced and fixed. |

### 5.1 D1 — evaluation drift: root causes

D1 has three separate causes. None of them changes a grounding violation count.

1. **All validation flags false — fixed (evaluation harness).** The synthetic candidates in
   `backend/data/evaluation/m4/cases/candidates.json` are hand-written structured data with no
   `parser_version`. Since `4699c7c`, `effective_parser_warnings()`
   (`backend/app/services/structured_resume.py`) treats a missing version as parser 1, older
   than the current `PARSER_VERSION` 4. It adds the "outdated parser — reprocess the file"
   warning, and `build_validation_result()` (`customization_validator.py`) never reports
   *passed* while a parser warning exists. For seeded fixtures there is no file to reprocess,
   so the warning measured nothing. **Proof:** the same evaluation with the version stamped
   gave 15/16 flags true; the remaining false flag is cause 2. **Fix:** `seed_candidate()` in
   `backend/app/services/m4_evaluation.py` now stamps the current `PARSER_VERSION` unless a
   fixture sets its own. Product validation rules are unchanged. Regression test:
   `test_m4_2_evaluation_framework.py::test_seeded_fixtures_are_current_parser_output_unless_they_say_otherwise`.
2. **One needs-review item — not changed, needs a decision.** For pair 7 (candidate PO × JOB-0121 DevOps Intern), the
   deterministic cover letter quotes a job responsibility: *My background in Git aligns
   directly with this role's focus on "Maintain CI/CD workflows" …*. `check_unsupported_claims()`
   (added in `4699c7c`) exempts quoted job text only from its *quoted-name* check. Its
   *technology* check still sees "CI/CD", so the sentence is removed and validation is not
   passed for that pair. This looks like a false positive: the sentence describes the role,
   not a candidate skill. But exempting it would loosen a validation rule, so it was left
   unchanged. The evaluation itself classifies it as "needs human review", not a violation.
3. **Fewer checks, different question counts and assistant text — tracked file is stale.** The
   tracked results were generated at 2026-10-10 05:00 UTC, before the final code of commit
   `4699c7c` (18:48 IST the same day). Example: the tracked assistant answer lists
   "Your projects: Library API." without technologies, but the final code includes them
   (`RESUME_PARSING_AUDIT.md` fix #10). No backend code changed after `4699c7c`. Interview
   question counts and the number of structured checks follow from the final parser and
   reliability changes in that commit.

**After the fix** (scratch run, 2026-10-17): every flag equals the tracked file except two.
Pair 7's customization flag is false (cause 2). Pair 3 (GA × JOB-0035)'s interview flag is true, where the
stale tracked file had false. The tracked results and the frozen M4.2 baseline were **not**
overwritten. Regenerating `m4_3_optimized_results.json` / `M4_3_OPTIMIZED_EVALUATION.md`
(run `scripts/run_m4_evaluation.py` without `--output-dir`) needs the author's approval.
After that, the README and technical doc §24 "needs-review 0" figure should read 1, unless
cause 2 is changed.

### 5.2 D2 — intermittent e2e failure: root cause and fix

Each `page.goto` reloads the app, which restores the active resume with
`GET /api/profiles/<id>/resumes`. The Skill Gaps page shows its "upload your resume" empty
state as soon as no resume ID is set, *before* that request returns. The test's assertion
therefore could pass while the request was still in flight, and the following `page.goto`
aborted it (`net::ERR_ABORTED`). The network guard reported this correctly.

- **Reproduced deterministically** with a temporary spec that held the request
  (`holdRequests`). All assertions passed, and the guard then failed with the identical
  `requestfailed … /resumes net::ERR_ABORTED`.
- **Fix (test only, `e2e/navigation.spec.ts`):** `gotoRestored()` waits for the app's real
  restore response after each navigation in that test, so the empty states are asserted on
  the settled page. The guard and its exemptions are unchanged.
- **Verified:** the fixed flow passed with the restore delayed by 2 s (temporary spec, deleted),
  and `navigation.spec.ts --repeat-each=10` gave 70 passed.
- **Remaining observation (not changed):** in the app, Skill Gaps (and Progress) briefly
  show their no-resume state while the restore is in flight. Showing a loading state instead
  would be a separate UI change.

## 6. Defect → regression-test traceability

Defects are listed in [`Defect_Tracker Template_v0.1.xlsx`](Defect_Tracker%20Template_v0.1.xlsx).

| Defects | Regression evidence |
|---|---|
| D-01 – D-11 | `test_pdf_extraction.py` (Skia fixture), `test_docx_extraction.py` (layout fixture), `test_section_detection.py`, `test_resume4_regressions.py`, `test_video_audit_regressions.py`, `test_customization_validator.py`; unit `routing.test.ts` (D-11) |
| D-12 – D-21 | e2e `responsive.spec.ts`, `resume-workflow.spec.ts`, `a11y.spec.ts`, `contrast.spec.ts`, `session-expiry.spec.ts`; `test_session_cookie.py` (D-21). D-14, D-15, D-18 and D-20 have no dedicated automated test. |
| D-22 – D-26 | `test_auth_persistence.py`, `test_cors.py`, `test_resume_parser_robustness.py`, `test_resume_parser_real_world.py`, `test_skill_gap_evidence.py`, `test_customization_quality.py` |
| D-27 – D-32 | e2e `lighting.spec.ts`, `session-expiry.spec.ts`, `resume-dependent.spec.ts`, `navigation.spec.ts`, `roadmap-lifecycle.spec.ts`; unit `profileCompletion.test.ts` |
