# Agile Methodology — AI Career Companion

Part of the Agile artifact set indexed in [README.md](README.md).

This document separates **what was actually practised** (with evidence) from
**recommended practice** for any further work. It does not claim Scrum ceremonies that
did not take place.

## 1. Project context

| Item | Value | Evidence |
|---|---|---|
| Project | AI Career Companion: resume-grounded career guidance web application | [`README.md`](../../README.md) |
| Programme | Infosys internship project | [`README.md`](../../README.md), [`FINAL_TECHNICAL_DOCUMENTATION.md`](../FINAL_TECHNICAL_DOCUMENTATION.md) |
| Team | One contributor in the Git history (`jeswinjarald-hash`). Mentor and reviewer names are not recorded in the repository. | `git shortlog -sne --all` |
| Period with recorded activity | 2026-08-28 (initial commit) to 2026-10-11 (latest commit); report work to 2026-10-16 | Git history; project report §7 |
| Deployment | None. Local development and evaluation only. | README "Production build requirements" |

## 2. Objectives and stakeholder needs

Objectives are from the technical documentation §3:

1. Extract structured, inspectable candidate context from a real resume (no OCR, no LLM).
2. Retrieve relevant opportunities semantically from a curated, validated knowledge base.
3. Score candidate–job fit with transparent, deterministic, weighted logic.
4. Make every generated statement traceable to candidate evidence.
5. Keep any LLM strictly subordinate: grounded input, validated output, deterministic fallback.
6. Persist each user's data under strict ownership.
7. Measure the workflow (M4.2), improve it under controlled experiments (M4.3), document it
   honestly (M4.4).

| Stakeholder | Need | Where addressed |
|---|---|---|
| Student (only application role) | Know which openings fit, what is missing, how to apply and prepare, and where each application stands | Backlog PB-01 – PB-17 |
| Internship mentor / evaluator | Understand how each score or generated sentence was derived; reproducible evidence | Explainable scores, grounding validator, evaluation artifacts, this folder |
| Developer (maintainer) | Change safely | Automated tests, frozen baseline, isolation guards |

## 3. Methodology actually followed

**Milestone-driven, iterative and incremental development by a single developer,** with
an evidence-first quality practice. It was *not* formal Scrum.

| Practice | Followed? | Evidence |
|---|---|---|
| Work divided into milestones (M1 → M4.4), each building on the previous one's output | Yes | milestone documents in [`docs/`](../); commit messages |
| Incremental delivery: each milestone ends with working, tested software | Yes | each feature commit includes tests (e.g. `479f02b` tracker + tests) |
| Review → fix cycles after a milestone | Yes | `509d53c` (M3.1 manual review), `19af562` (parser audit), `4699c7c` (audits) |
| Measured improvement against a frozen baseline | Yes | M4.2 baseline, M4.3 experiment log |
| Documentation written per milestone | Yes | one document per milestone |
| Product backlog, user stories, estimates | **No** — reconstructed afterwards in this folder | — |
| Time-boxed sprints, sprint planning, burndown, velocity | **No** | no records |
| Daily stand-ups, sprint reviews, retrospectives | **No** | no records; a retrospective was reconstructed in [RETROSPECTIVE.md](RETROSPECTIVE.md) |
| Issue tracker / board | **No** | — |
| Continuous integration | **No** | no CI configuration in the repository |

### Development workflow (as practised)

```text
Milestone goal (milestone document)
  → implement backend service + API + schema
  → add pytest unit/service/API tests (incl. auth and cross-user checks)
  → connect the React view through a typed service in src/services/
  → manual browser check against a scratch database
  → write or update the milestone document
  → commit on develop (later: feature branch)
  → review findings → fix commit(s) with regression tests
```

### Version control practice

| Aspect | Actual |
|---|---|
| Branches | `main` (initial commit only), `develop` (milestones M1–M4.4 and audits), `feature/ui-redesign-skill-graph` (UI redesign, e2e, isolation) |
| Commit style | Conventional prefixes (`feat:`, `fix:`, `docs:`, `chore:`) |
| Commit size | Mostly one milestone per commit; some very large commits (`81e7035`, `024a63d`) |
| Pull requests / code review | None recorded |
| Secrets and personal data | `.env`, databases, resumes and the FAISS index are gitignored (technical doc §30). Older history still contains personal data that was later removed from a test fixture ([RESUME_PARSING_AUDIT.md](../RESUME_PARSING_AUDIT.md) §4). |

### Quality practice

- Backend: pytest unit, service, API and evaluation-backed tests; strict `xfail` for known
  weaknesses; enforced isolation from the real database, resume store and network
  (`CLAUDE.md` "Test isolation").
- Frontend: strict TypeScript, ESLint, Playwright unit tests (`tests/unit/`) and e2e tests
  (`e2e/`, feature branch), including axe accessibility and rendered-pixel contrast checks.
- API contract: generated types (`npm run api:check`) and `src/api/contract.check.ts`.
- Rule: no mock or fabricated data in the application (`CLAUDE.md` "Rules").

## 4. Completion criteria

Completion criteria are defined in [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md). They are
written down for the first time in this folder, but are drawn from the gates the project
already ran at M4.4 (technical doc §21) and from `CLAUDE.md` "Verification".

## 5. Recommended practice for further work (not yet followed)

1. Keep [PRODUCT_BACKLOG.md](PRODUCT_BACKLOG.md) as the live backlog, or move it into GitHub
   Issues with a project board; one issue per story ID.
2. Use one-week time-boxes, each with a goal chosen from the top of the backlog.
3. One branch and one pull request per story, merged into `develop` after the
   Definition-of-Done gates pass; release `develop` → `main` at milestone ends.
4. Run the gates automatically in CI.
5. Hold a short written review and retrospective at the end of each time-box, using the
   *Retrospection* sheet of the Agile template.
6. Record defects in the Defect Tracker when they are found, not afterwards.
