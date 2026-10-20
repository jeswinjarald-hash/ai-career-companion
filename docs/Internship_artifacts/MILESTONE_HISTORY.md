# Milestone History (Retrospective Sprint Record) — AI Career Companion

Part of the Agile artifact set indexed in [README.md](README.md). The task-level view of
the same phases is on the *Sprint Backlog* sheet of
[`Agile_Template_v0.1.xls`](Agile_Template_v0.1.xls).

## What evidence exists

| Evidence | Exists? |
|---|---|
| Milestone definitions (M1, M2.1–M2.4, M3.1–M3.4, M4.1–M4.4) | Yes — milestone documents in [`docs/`](../) and [`FINAL_TECHNICAL_DOCUMENTATION.md`](../FINAL_TECHNICAL_DOCUMENTATION.md) §15–§20 |
| Commit dates for each milestone's delivery | Yes — 19 commits by one author (`jeswinjarald-hash`), 2026-08-28 to 2026-10-11 |
| Sprint plans, sprint start dates, sprint goals agreed in advance | **No** |
| Story points, effort estimates, burndown, velocity | **No** |
| Daily stand-ups, sprint reviews, sprint retrospectives, mentor review minutes | **No** |
| Issue tracker / board | **No** (no GitHub issues or project board referenced in the repository) |

The project was therefore **milestone-driven and iterative, not formal Scrum**. The phases
below are *retrospective development phases*. Their boundaries are commit dates. A
phase's start date is the previous phase's last commit; actual working days are unknown.
Nothing below is a planned sprint, and no estimates or velocity are given because none were
recorded.

## Phases

| Phase | Milestones delivered | Commits (date) | Branch where it lives | Main outcome | Evidence |
|---|---|---|---|---|---|
| P0 Set-up | — | `973beb4` (2026-08-28) | `main` | Repository initialised | Git history |
| P1 Foundation | M1 candidate understanding; M2.1 knowledge base (180 internship records); M2.2 semantic retrieval; M2.3 matching; M2.4 evaluation; authentication and per-user ownership | `81e7035` (2026-09-17) — single commit | `develop` | Resume pipeline, FAISS search, deterministic matching, session auth, M2.4 results | [`MILESTONE_1.md`](../MILESTONE_1.md), [`MILESTONE_2_2.md`](../MILESTONE_2_2.md), [`MILESTONE_2_3.md`](../MILESTONE_2_3.md), `backend/data/evaluation/results/` |
| P2 Skill gap | M3.1 Skill Gap Analysis agent; manual-review fixes; SQLite path and parser fixes | `a90e498` (09-18), `509d53c` (09-19), `2e16893` (09-19) | `develop` | Evidence-based gap analysis and readiness | [`MILESTONE_3_1.md`](../MILESTONE_3_1.md) |
| P3 Generation agents | Parser robustness audit; CORS fix; M3.2 customization (+ LLM rewrite layer, quality fix); M3.3 interview prep; M3.4 assistant; career-opportunity generalization (320 records) | `19af562`, `f202ca1`, `b866c71`, `9e4b4cd` (09-23); `9834d11`, `d4d3c49`, `dfcbc76`, `e532ad0`, `688262b` (09-24) | `develop` | Grounded customization, interview prep, assistant, generalised catalogue | [`MILESTONE_3_2.md`](../MILESTONE_3_2.md) – [`MILESTONE_3_4.md`](../MILESTONE_3_4.md), [`CAREER_OPPORTUNITY_GENERALIZATION.md`](../CAREER_OPPORTUNITY_GENERALIZATION.md) |
| P4 Tracking, evaluation, release docs | M4.1 tracker; M4.2 baseline evaluation; M4.3 optimisation; M4.4 documentation and release audit | `479f02b`, `901e574` (2026-10-05) | `develop` | Tracker; 464 passed / 1 xfailed at M4.4 | [`MILESTONE_4.md`](../MILESTONE_4.md), technical doc §19–§21 |
| P5 Hardening | Resume-parsing and grounding audit; UI/UX polish | `4699c7c` (2026-10-10) | `develop` | Parser version 4; 547 passed / 1 xfailed | [`RESUME_PARSING_AUDIT.md`](../RESUME_PARSING_AUDIT.md), [`UI_UX_POLISH_REPORT.md`](../UI_UX_POLISH_REPORT.md) |
| P6 UI redesign and test isolation | Aurora Prism redesign; Playwright e2e suite; enforced test isolation; route-aware skill-graph background; card-highlight fix | `024a63d`, `cd30486` (2026-10-11) | `feature/ui-redesign-skill-graph` (pushed, **not merged**) | e2e + unit suites; isolation guards | `CLAUDE.md`, `e2e/`, `tests/unit/` |
| P7 Final reporting | Project report, technical documentation exports, these Agile artifacts | release commits on `main` | `main` | Report dated re-run 2026-10-16; audit evidence dated 2026-10-17 | [`docs/project-report/`](../project-report/README.md) |

Elapsed calendar time from P0 to P6 is 44 days (2026-08-28 to 2026-10-11). P1 covers 20 of
those days with a single commit, so the order of work inside P1 is not recorded.

## Phase goals and results

Goals below are taken from each milestone document's stated objective, not from a sprint
planning record.

| Phase | Goal (from milestone docs) | Result | Not achieved / carried over |
|---|---|---|---|
| P1 | Turn a profile and PDF/DOCX resume into structured candidate context; retrieve and score opportunities | Achieved; 27 backend tests at M1 (MILESTONE_1 §Testing) | Authentication was deferred in M1 and added in this same commit |
| P2 | Explainable requirement-by-requirement skill gap | Achieved, followed by fixes from a manual review | — |
| P3 | Grounded generation (customization, interview prep, assistant) with optional LLM | Achieved | General career questions (CV06) unresolved |
| P4 | Tracker; measure the whole workflow; optimise under controlled experiments; document honestly | Achieved; 6 → 1 strict `xfail` | Matching margins below targets (technical doc §26.2) |
| P5 | Fix parsing/grounding defects seen on real resumes; UI readiness | Achieved; defects recorded in the Defect Tracker | — |
| P6 | Redesign UI without fabricated data; automated browser tests; isolate tests from real data | Implemented and validated | — |
| P7 | Submission documents | Completed; release documentation and license added | — |

## Branch state on 2026-10-17

| Branch | Head | Contains |
|---|---|---|
| `main` (`origin/main`, GitHub default) | release head | P1–P7 after the verified release integration |
| `develop` (`origin/develop`) | `4699c7c` | P1–P5 |
| `feature/ui-redesign-skill-graph` (`origin/…`) | `cd30486` | P1–P6 |

A reviewer opening the GitHub repository on its default branch will see the verified
implementation and submission documentation. The historical branch comparison above
records the state before release integration.
