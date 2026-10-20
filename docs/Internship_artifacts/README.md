# Internship Agile Artifacts — AI Career Companion

This folder holds the Agile project artifacts for the Infosys internship submission. The
three Excel files are the Infosys templates, now filled in. The Markdown files hold the
same information in more detail and can be read on GitHub (GitHub does not render `.xls`
or `.xlsx`).

**Audit evidence date:** 2026-10-17. The final release integrates the verified implementation
and these artifacts on `main`; the dated evidence below retains the state observed during
the audit.

## 1. How to read these artifacts

The project was developed **milestone by milestone by a single developer**. It did not use
formal Scrum. No backlog, sprint plan, stand-up notes, sprint review, retrospective or defect
log was kept during development. Every artifact here was therefore **reconstructed from
evidence in the repository**: source code, API routes, tests, milestone and audit documents,
and Git history. Each artifact says so. Where a fact could not be established, it is marked
*Not recorded*. No dates, estimates, meetings, team members or results have been invented.

## 2. Documents

| Document | Purpose |
|---|---|
| [AGILE_METHODOLOGY.md](AGILE_METHODOLOGY.md) | Methodology actually followed (and what was not), objectives, stakeholders, workflow, version-control and quality practice, recommended future practice |
| [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md) | Evidence-based feature inventory and the 25-item product backlog (PB-01 – PB-25) with retrospective MoSCoW priority, status, dependencies, evidence and limitations |
| [USER_STORIES.md](USER_STORIES.md) | 21 user stories (US-01 – US-21) with preconditions, Given/When/Then acceptance criteria, edge cases and the test that verifies each criterion |
| [MILESTONE_HISTORY.md](MILESTONE_HISTORY.md) | Retrospective development phases P0 – P7, built from the 19 commits and milestone documents; branch state |
| [RETROSPECTIVE.md](RETROSPECTIVE.md) | Reviews that did happen, strengths, challenges, technical debt, testing gaps, lessons and action items |
| [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) | Story-level and release-level Definition of Done, and the current status of each gate with evidence |
| [TRACEABILITY_MATRIX.md](TRACEABILITY_MATRIX.md) | Requirement → backlog → story/AC → implementation → test → status; the 2026-10-17 verification run; discrepancies; defect → regression test |
| [`Agile_Template_v0.1.xls`](Agile_Template_v0.1.xls) | Infosys Agile template: *Product Backlog* (25 items), *Sprint Backlog* (26 phase tasks from Git history), *Stand up Meeting* (states that no records exist), *Retrospection* (7 phases, reconstructed) |
| [`Defect_Tracker Template_v0.1.xlsx`](Defect_Tracker%20Template_v0.1.xlsx) | 32 real defects (D-01 – D-32) from the audit reports, fix commits and e2e regression specs |
| [`Unit_Test_Plan_v0.1.xlsx`](Unit_Test_Plan_v0.1.xlsx) | 30 test cases (TC-01 – TC-30) with actual results from the 2026-10-17 run |

### Related project documentation

| Document | Content |
|---|---|
| [`../../README.md`](../../README.md) | Project overview, quick start, evaluation summary |
| [`../FINAL_TECHNICAL_DOCUMENTATION.md`](../FINAL_TECHNICAL_DOCUMENTATION.md) | Canonical technical documentation (M4.4) |
| [`../project-report/AI_Career_Companion_Project_Report.md`](../project-report/AI_Career_Companion_Project_Report.md) | Internship project report (source of FR/NFR/UC/TC IDs) |
| [`../MILESTONE_1.md`](../MILESTONE_1.md), [`../MILESTONE_2_2.md`](../MILESTONE_2_2.md), [`../MILESTONE_2_3.md`](../MILESTONE_2_3.md), [`../MILESTONE_3_1.md`](../MILESTONE_3_1.md) – [`../MILESTONE_3_4.md`](../MILESTONE_3_4.md), [`../MILESTONE_4.md`](../MILESTONE_4.md) | Milestone documents |
| [`../RESUME_PARSING_AUDIT.md`](../RESUME_PARSING_AUDIT.md), [`../UI_UX_POLISH_REPORT.md`](../UI_UX_POLISH_REPORT.md) | Audit reports (sources of defects D-01 – D-21) |
| [`../CAREER_OPPORTUNITY_GENERALIZATION.md`](../CAREER_OPPORTUNITY_GENERALIZATION.md), [`../file-purpose-guide.md`](../file-purpose-guide.md) | Dataset generalisation; file guide |

## 3. Snapshot of the project (verified 2026-10-17)

| Area | Result |
|---|---|
| Features done and tested | Accounts, profile, resume pipeline, candidate context, semantic search, matching, skill gap, customization, interview prep, tracker, isolation, offline evaluation |
| Partial | Career assistant (general questions, CV06); Settings (informational only) |
| Not implemented | Learning roadmap, deployment, production hardening |
| Previously only on the feature branch; now released to `main` | UI redesign, e2e suite, skill-graph background, enforced test isolation, dashboard insight/profile-completion modules |
| Backend tests | 556 passed, 1 xfailed (expected) — after the follow-up fix |
| Frontend unit tests | 80 passed |
| Browser (e2e) tests | 97 passed after the follow-up fix (first run: 96 passed, 1 intermittent failure) |
| Type check / lint / API contract / build / dataset validation | All passed |
| Offline evaluation | 0 grounding violations. The harness defect is fixed; 1 needs-review item awaits a decision; tracked results are stale (TRACEABILITY_MATRIX §5.1) |

## 4. Audit of the original artifacts and corrections

### 4.1 What was here before this audit

| File | Purpose | State found |
|---|---|---|
| `Agile_Template_v0.1.xls` | Infosys Agile template (Product Backlog, Sprint Backlog, Stand-up, Retrospection) | **Blank template.** Headers only; Sprint Backlog sheet password-protected (data cells editable). |
| `Defect_Tracker Template_v0.1.xlsx` | Infosys defect tracker | **Blank template** (Defects sheet + type list) |
| `Unit_Test_Plan_v0.1.xlsx` | Infosys unit test plan | **Blank template** (UT sheet headers only) |

There was no backlog content, no user stories, no sprint or milestone record, no
retrospective, no Definition of Done and no traceability. All three files were untracked
by Git.

### 4.2 Audit checklist (before editing)

| Check | Finding |
|---|---|
| Missing sections | All content missing (templates were blank) |
| Outdated / inconsistent information | Not applicable to the templates. Found in the related documentation instead — see 4.4 |
| Backlog completeness, story quality, acceptance criteria | None existed. Written from the implemented features (PRODUCT_BACKLOG, USER_STORIES) |
| Sprint / milestone information | No sprint records. Phases reconstructed from Git history, labelled retrospective |
| Testing evidence | Existed in the repository but was not linked to requirements. Linked in TRACEABILITY_MATRIX, re-run on 2026-10-17 |
| Dates and timelines | Only commit dates exist. Detection, start and meeting dates are marked *Not recorded* |
| Links | New Markdown uses relative links; the file name with a space is linked as `Defect_Tracker%20Template_v0.1.xlsx` |
| Unsupported claims | None added. Every status cites a test, commit or document |
| Template issues | *Sprint Backlog* rows 10–22 have stray drop-down lists on the "Task Completion Date" (Activity list) and "Team Member" (Status list) columns. The values entered follow the column headers. MoSCoW, Status, Activity and Type of Defect values use the templates' own lists. |

### 4.3 Files changed in this audit

| File | Change |
|---|---|
| `Agile_Template_v0.1.xls` | Filled all four sheets. Template layout, protection and header formatting kept; the Sprint Backlog title row is locked, so the note is in row 5. |
| `Defect_Tracker Template_v0.1.xlsx` | 32 defects entered |
| `Unit_Test_Plan_v0.1.xlsx` | 30 test cases entered |
| 8 new Markdown files (this README and the 7 documents above) | Created because the templates cannot hold Given/When/Then criteria, traceability or narrative, and GitHub cannot display Excel files |

The blank originals were backed up outside the repository before editing. The audit itself
modified no file outside `docs/Internship_artifacts/`.

A follow-up on 2026-10-17 fixed the two problems the audit found (TRACEABILITY_MATRIX §5.1,
§5.2). It changed three tracked files before release integration:
`backend/app/services/m4_evaluation.py` (evaluation harness: stamp the parser version on
seeded fixtures), `backend/tests/test_m4_2_evaluation_framework.py` (regression test) and
`e2e/navigation.spec.ts` (await the resume restore before navigating). No product
validation rule and no network-guard rule was changed.

### 4.4 Discrepancies found in the related documentation (not edited here)

| # | Document | Statement | Actual (evidence) |
|---|---|---|---|
| 1 | `FINAL_TECHNICAL_DOCUMENTATION.md` §22 | "The cookie is set with `secure=False` because the project runs over local HTTP." | Since `4699c7c` the cookie is `Secure` whenever `APP_ENV != development` (`backend/app/core/config.py` `session_cookie_secure`; `test_session_cookie.py`). README "Production build requirements" is correct. |
| 2 | `FINAL_TECHNICAL_DOCUMENTATION.md` §21, §26.12; `UI_UX_POLISH_REPORT.md` §4 | "There is no automated frontend test framework" / "no automated UI tests" | True for `develop`. On `feature/ui-redesign-skill-graph` there are 80 unit tests (`tests/unit/`) and 97 Playwright e2e tests (`e2e/`). |
| 3 | `FINAL_TECHNICAL_DOCUMENTATION.md` §21 vs §26.12 | §21: ESLint "1 warning"; §26.12: "ESLint reports no warnings" | Both were true at different dates (warning fixed in `4699c7c`). Lint is clean on 2026-10-17. |
| 4 | `README.md`, technical doc §24 | "Grounding … needs-review items 0 / 0"; results "reproduced identically" | The tracked results predate the final code of `4699c7c`. A fresh run gives 0 violations but 1 needs-review item (a cover-letter sentence quoting "CI/CD" from the job, removed by the validator). The false validation flags were an evaluation-harness defect, now fixed. TRACEABILITY_MATRIX §5.1. |
| 5 | `MILESTONE_1.md` "Limitations" | Authentication deferred; recommendations and skill gap are "mock/demo modules" | Historical statement from before `81e7035`; the technical doc §15 already notes this. Kept as history. |
| 6 | Root `README.md` "Documentation" table | Does not list `docs/project-report/` or this folder | Both are untracked. Add links when they are committed. |

These documents are outside this folder's scope, so they were not edited. Item 4 also needs
investigation in code before any document is changed.

## 5. Git and GitHub readiness

| Path | Git status | Ignored? | To appear on GitHub |
|---|---|---|---|
| `docs/Internship_artifacts/*` (11 files) | **Untracked** | No | `git add docs/Internship_artifacts`, commit, push |
| `docs/project-report/` | Untracked | No | Commit if it is meant to be submitted |
| `docs/FINAL.pdf`, `docs/FINAL_TECHNICAL_DOCUMENTATION*.docx/.pdf` | Untracked | No | Decide whether to commit generated exports. The Markdown source is tracked. |
| `docs/~$NAL_TECHNICAL_DOCUMENTATION2.docx` | Ignored (`.gitignore:51` `~$*`) | Yes | Should not be committed (Office lock file) |
| `.claude/` | Untracked | No | Keep untracked (local tool configuration, `CLAUDE.md` "Git") |
| All other documentation in `docs/*.md` | Tracked, unmodified | — | Already on `origin/develop` |

**Important — what GitHub shows today:**

| Remote branch | Head | Content |
|---|---|---|
| `origin/main` (default branch) | `973beb4` | Initial commit only |
| `origin/develop` | `4699c7c` | M1 – M4.4 and the audits |
| `origin/feature/ui-redesign-skill-graph` | `cd30486` | Above + UI redesign, e2e tests, isolation |

A reviewer who opens the repository on GitHub sees the default branch, `main`, which has
none of the project. Before submission:

1. Get approval, then commit this folder on the working branch (never on `main` directly).
   Do not include `.claude/` or the `~$` lock file.
2. Merge `feature/ui-redesign-skill-graph` → `develop` → `main` (or change the GitHub default
   branch), after the gates in [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) pass.
3. Push the branches. No force-push is needed.

**Privacy check before pushing:**
- The Excel files' metadata names Infosys staff as template authors (e.g.
  `Sumeet_Kumar08@infosys.com`; "Kamaljeet Kaur01"). Saving them in Excel set *Last Saved
  By* to the local Office user name. Remove these with Excel's *File → Info → Check for
  Issues → Inspect Document* if they should not be public.
- These artifacts contain no credentials, `.env` values, resumes, databases or personal data
  beyond the Git author name.
- Older Git history still contains personal data that was later removed from a test fixture
  ([`RESUME_PARSING_AUDIT.md`](../RESUME_PARSING_AUDIT.md) §4). Rewriting history is a
  separate decision and is **not** recommended without care, because it requires a force-push.
