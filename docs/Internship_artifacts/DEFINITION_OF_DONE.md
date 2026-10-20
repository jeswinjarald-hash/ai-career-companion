# Definition of Done — AI Career Companion

Part of the Agile artifact set indexed in [README.md](README.md).

No Definition of Done was written during development. This one was written on 2026-10-17
from the release gates the project actually ran at M4.4
([`FINAL_TECHNICAL_DOCUMENTATION.md`](../FINAL_TECHNICAL_DOCUMENTATION.md) §21) and the
verification rules in `CLAUDE.md`. Each criterion can be tested. The last column of §3 shows
whether the current code meets it, and the evidence. A criterion is marked **Met** only when
evidence exists.

## 1. Story-level Definition of Done

A backlog item is *Done* when all of the following hold:

| # | Criterion | How it is checked |
|---|---|---|
| S1 | Every acceptance criterion in [USER_STORIES.md](USER_STORIES.md) has at least one automated test or a recorded manual check. | [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md) has no blank "Verification" cell for the story |
| S2 | Backend changes have unit/service tests **and** API tests that cover the 401 (no session) and 404 (another user's object) cases. | `*_requires_authentication` and cross-user tests in the module |
| S3 | User-visible behaviour on a page is covered by a Playwright e2e test, or the manual check is recorded in a milestone or audit document. | `e2e/*.spec.ts` or milestone doc |
| S4 | Every number, score, chart, status or list shown comes from an API response or a persisted value. Unimplemented features say so. Unavailable values show "Not available", not 0. | Code review against `CLAUDE.md` "Rules"; `insights.ts` tests |
| S5 | Generated text is checked by the grounding validator; any LLM failure falls back to the deterministic result. | `customization_validator.py` tests; `test_customization_llm.py` |
| S6 | Errors are shown in readable form (`apiDetailMessage`), with a retry where the action can be repeated. No unhandled promise rejections. | e2e error-state tests; network guard in `e2e/support/fixtures.ts` |
| S7 | Backend routes, schemas and the database schema are unchanged unless approved. After an approved change, `npm run api:types` is run and `npx tsc -b` passes. | `npm run api:check` |
| S8 | Tests use only synthetic data, never the real resume store, database or a live LLM. | `backend/tests/test_isolation.py`, `e2e/isolation.spec.ts` |
| S9 | The relevant milestone or technical document is updated, and any limitation is stated. | Diff review |
| S10 | No secrets, `.env` values, personal data, databases, resumes or build output are added to Git. | `git status`, `git diff --stat` review |

## 2. Release-level Definition of Done (all gates)

| # | Gate | Command (Windows, repository root unless noted) |
|---|---|---|
| R1 | Type check | `npx tsc -b` |
| R2 | Lint | `npm run lint` |
| R3 | API contract | `npm run api:check` |
| R4 | Frontend unit tests | `npm run test:unit` |
| R5 | Backend tests (from `backend/`) | `..\.venv\Scripts\python.exe -m pytest -q` |
| R6 | Browser tests | `npm run test:e2e` |
| R7 | Build to a temporary directory | `npx vite build --outDir <temp dir> --emptyOutDir` |
| R8 | Dataset validation (from `backend/`) | `..\.venv\Scripts\python.exe scripts\validate_job_dataset.py` |
| R9 | Offline evaluation unchanged or improved (from `backend/`) | `..\.venv\Scripts\python.exe scripts\run_m4_evaluation.py --output-dir <temp dir>` |
| R10 | Manual demo workflow (technical doc §25) on a fresh scratch database | Recorded result |
| R11 | Work merged to the branch reviewers will read (`main`) | `git log origin/main` |
| R12 | Documentation (README, technical doc, these artifacts) consistent with the code | Review |

## 3. Status of the current code against the release DoD (2026-10-17)

Checked on the working tree of `feature/ui-redesign-skill-graph` at `cd30486`, which contains
all of `develop`. The only uncommitted changes were documentation.

| Gate | Status | Evidence |
|---|---|---|
| R1 Type check | **Met** | `npx tsc -b`: exit 0 (2026-10-17) |
| R2 Lint | **Met** | `npm run lint`: exit 0, no problems reported (2026-10-17) |
| R3 API contract | **Met** | "API types match the backend schema (python 3.12.3, fastapi 0.141.1, pydantic 2.13.5, openapi-typescript 7.13.0)" (2026-10-17) |
| R4 Frontend unit tests | **Met** | 80 passed (2026-10-17) |
| R5 Backend tests | **Met** | 555 passed, 1 xfailed (CV06, expected), 2 third-party deprecation warnings, 47.7 s; after the follow-up fix, 556 passed, 1 xfailed (2026-10-17) |
| R6 Browser tests | **Met** (uncommitted fix) | First run: 96 passed, 1 intermittent failure. Root cause found and fixed in `e2e/navigation.spec.ts` ([TRACEABILITY_MATRIX.md §5.2](TRACEABILITY_MATRIX.md#52-d2--intermittent-e2e-failure-root-cause-and-fix)). Re-run: 97 passed, 0 failed (2026-10-17) |
| R7 Build | **Met** | `npx vite build` to a scratch directory succeeded (2026-10-17) |
| R8 Dataset validation | **Met** | `"status": "PASS"` (2026-10-17) |
| R9 Evaluation | **Partly met** | Ran offline (2026-10-17): 0 grounding violations; retrieval, matching, consistency and hand-off unchanged. The cause of the false validation flags was fixed in the evaluation harness. Still open: 1 needs-review item awaiting a decision, and the tracked results predate the final code and need regenerating (approval required) — [TRACEABILITY_MATRIX.md §5.1](TRACEABILITY_MATRIX.md#51-d1--evaluation-drift-root-causes) |
| R10 Manual demo | Not re-run since 2026-10-05 | Technical doc §25 (M4.4 manual validation) |
| R11 Merged to `main` | **Met after release integration** | Verified release commits are pushed to `origin/main` |
| R12 Documentation consistent | **Partly met** | Discrepancies listed in [README.md §4](README.md#4-audit-of-the-original-artifacts-and-corrections) |

## 4. Story-level status summary

| Status | Backlog items |
|---|---|
| Meets story DoD | PB-01, PB-03, PB-05 – PB-12, PB-14, PB-15, PB-18, PB-19 |
| Meets story DoD after release integration | PB-02, PB-04, PB-16, PB-20, PB-21 |
| Does not meet DoD | PB-13 (CV06 acceptance criterion fails), PB-17 (live-model criterion not verified), PB-22 – PB-25 (not implemented) |
