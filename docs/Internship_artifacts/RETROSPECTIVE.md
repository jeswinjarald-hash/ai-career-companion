# Retrospective Engineering Review — AI Career Companion

Part of the Agile artifact set indexed in [README.md](README.md). The Start / Stop /
Continue summary is also on the *Retrospection* sheet of
[`Agile_Template_v0.1.xls`](Agile_Template_v0.1.xls).

**Nature of this review.** No sprint retrospectives, sprint reviews or mentor feedback were
recorded during the project. This is a **retrospective engineering review written on
2026-10-17** from evidence in the repository: the Git history, the milestone documents, the
audit reports and the test results. It is not a record of meetings. Where it states a
lesson, the evidence for it is cited.

## 1. Reviews that did happen (documented in the repository)

| Review | Date | Evidence | Outcome |
|---|---|---|---|
| M3.1 manual review | 2026-09-19 | commit `509d53c` "resolve M3.1 manual-review findings" | Project count, soft-skill matching, learning-only evidence and evidence noise fixed |
| Resume parser robustness audit | 2026-09-23 | commit `19af562`; [`MILESTONE_1.md`](../MILESTONE_1.md) "Resume Parser Robustness Audit" | Fragmented projects and prose-word skills fixed; `parser_warnings` added |
| M4.2 baseline evaluation | before 2026-10-05 | `backend/data/evaluation/m4/results/M4_2_BASELINE_REPORT.md` | Weaknesses recorded; 6 encoded as strict `xfail` tests |
| M4.3 controlled experiments | before 2026-10-05 | `m4_3_experiments.json`; technical doc §20 | 11 changes accepted (incl. T1 instrumentation), 6 rejected or deferred, 1 prompt review with no change — each with a recorded reason |
| M4.4 release audit | 2026-10-05 | technical doc §21, §25, §30 | All gates passed; 13-step manual demo passed on a scratch database |
| Resume-parsing and grounding audit | 2026-10-10 | [`RESUME_PARSING_AUDIT.md`](../RESUME_PARSING_AUDIT.md) | 11 root causes fixed (Defect Tracker D-01 – D-11) |
| UI/UX polish audit | 2026-10-10 | [`UI_UX_POLISH_REPORT.md`](../UI_UX_POLISH_REPORT.md) | P1/P2 defects fixed (Defect Tracker D-12 – D-21) |
| UI redesign defect review (defects "A"–"E" in e2e specs) | fixed in `024a63d` (2026-10-11); detection date not recorded | comments in `e2e/session-expiry.spec.ts`, `navigation.spec.ts`, `resume-dependent.spec.ts`, `roadmap-lifecycle.spec.ts` | 5 defects fixed with regression tests (Defect Tracker D-28 – D-32) |
| This documentation audit | 2026-10-17 | this folder | Discrepancies listed in [README.md §4](README.md#4-audit-of-the-original-artifacts-and-corrections) |

Who performed each review is not recorded beyond the single Git author.

## 2. What went well

- **Measured, reversible optimisation.** Every M4.3 change was measured alone against a
  frozen baseline, and rejected experiments are kept with their reasons (E3a–E3c, E8-V1,
  E8-V2). Strict `xfail`s went from 6 to 1.
- **Grounding as a hard rule.** A sentence-level validator plus fault injection (10/10
  detected) and zero grounding violations in the final evaluation.
- **Honest UI.** Empty states instead of placeholder figures. Unimplemented features (Learning
  Roadmap) say so. This is enforced by e2e tests (`navigation.spec.ts`, `charts.spec.ts`).
- **Ownership checks everywhere.** Each API test module has an authentication test and a
  cross-user 404 test.
- **Test isolation that is enforced, not just configured.** On the feature branch, an audit hook
  refuses access to the real database and resume store and blocks non-loopback network access
  (`backend/tests/test_isolation.py`, `e2e/isolation.spec.ts`).
- **Growing regression net.** Backend tests: 27 (M1) → 464 (M4.4) → 547 (2026-10-10) → 555
  (2026-10-17 run).

## 3. What was difficult

| Challenge | Evidence | Effect |
|---|---|---|
| Real-world resume layouts | `19af562`, `2e16893`, `4699c7c`; RESUME_PARSING_AUDIT §1 | Parsing was fixed three times; parser versioning and reprocessing were added |
| Large, infrequent commits | `81e7035` holds M1 + M2 + auth; `024a63d` changes 84 files (+17 729 lines) | Intermediate history is not reviewable; phase timing is only approximate |
| Matching score margins | technical doc §20 E3a–E3c, §26.2 | Targets A−B ≥ 10 and C−D ≥ 10 not met |
| General career questions without an LLM | strict `xfail` CV06 | Assistant story only partly done |
| Frontend tests arrived late | No automated UI tests until P6 (technical doc §26.12) | UI defects D-12 – D-21 were found manually |

## 4. Technical debt and gaps

1. Before release integration, `main` held only the initial commit; the verified
   implementation was on `develop` and the feature branch. The release now publishes
   the verified state on `main`.
2. No schema migrations (`create_all` plus one ad-hoc column helper).
3. Unused legacy tables: `selected_jobs`, `learning_roadmaps`, `roadmap_items`,
   `progress_events`.
4. Single-process in-memory caches.
5. Security scope is local only: no CSRF tokens, rate limiting, password reset or audit log.
6. No CI pipeline, so the gates in [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) are run by
   hand.
7. Node 18 is end-of-life, so `@playwright/test` is pinned to 1.61.1 (`CLAUDE.md`, Toolchain).
8. The live LLM path has not been evaluated.

## 5. Testing gaps

| Gap | Where it shows |
|---|---|
| No live-LLM evaluation | technical doc §26.4 |
| Evaluation set small and synthetic; labels rule-based, not human-judged | technical doc §26.5 |
| Learning Roadmap has no feature to test; only its context panel is tested | `roadmap-lifecycle.spec.ts` |
| Tracker reminder UI ("Upcoming actions") has no dedicated e2e test; logic is tested at service level | `test_application_service.py`; no matching e2e spec |
| Customization / interview-prep pages have no dedicated e2e spec; covered by API tests and the M4.4 manual demo | e2e folder listing |
| No load, concurrency or penetration testing (one concurrency probe in RESUME_PARSING_AUDIT D-09 only) | technical doc §22 |

## 6. Lessons learned

1. **Test with real-shaped input early.** Synthetic, well-formed resumes hid the parser
   defects that real Google Docs and Word files exposed (D-01 – D-05).
2. **Freeze a baseline before optimising.** Without M4.2, the regressions caused by E3a–E3c
   would have looked like improvements.
3. **Small commits per story.** Single large commits made this retrospective reconstruction
   approximate.
4. **Write the backlog and Definition of Done first.** They had to be reconstructed here
   because they were not kept during development.

## 7. Action items (proposed, not yet done)

| # | Action | Owner | Status |
|---|---|---|---|
| A1 | Merge `feature/ui-redesign-skill-graph` → `develop` → `main` after review, so GitHub's default branch shows the project | Project author | Open — needs approval |
| A2 | Commit this `docs/Internship_artifacts/` folder | Project author | Open — needs approval |
| A3 | Use GitHub Issues and small per-story commits/PRs for any further work | Project author | Proposed |
| A4 | Add a CI workflow running the Definition-of-Done gates | Project author | Proposed |
| A5 | Evaluate the LLM path on a fixed prompt set; resolve CV06 | Project author | Proposed |
| A6 | Update `FINAL_TECHNICAL_DOCUMENTATION.md` §22 and §26.12 for the feature-branch changes (see README §4) | Project author | Open |
