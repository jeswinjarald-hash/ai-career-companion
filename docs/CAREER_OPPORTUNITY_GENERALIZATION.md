# Career Opportunity Generalization

Generalizes the project from an internship-only system to a broader career-opportunity
system — internships, entry-level jobs, graduate programs, trainee, and apprenticeship
roles — while preserving the original AI Career Companion objective and every existing
milestone's behavior. This is a **dataset + terminology + minimal schema** change, not
a rebuild: M2's matching, M3.1's skill gap, M3.2's customization, M3.3's interview
preparation, and M3.4's orchestration all needed **zero scoring/generation logic
changes** — they were already driven by the actual job posting's real field content
(required skills, experience-requirement text, job title), never by a hardcoded
assumption that every posting is an internship.

## 1. Original dataset audit

The canonical dataset (`backend/data/internships/internship_jobs_180.json`, 180
records) was audited before any change:

- **`employment_type` distribution**: 150 `"Internship"`, 30 `"Entry Level"` — not
  literally internship-only, but internship-dominated (83%).
- **A real data quality finding**: all 30 `"Entry Level"` records still have a
  `job_title` that literally says "...Intern" (e.g. `JOB-0035`, `employment_type:
  "Entry Level"`, `job_title: "FastAPI Intern"`) — a pre-existing generation quirk
  from the original M2.1 build, not something this change introduced. These 30
  records are kept byte-for-byte unchanged (per the backward-compatibility
  requirement), and documented here rather than silently "fixed", since every
  milestone's tests and prior live-validation sessions (M3.2/M3.3/M3.4) already
  reference `JOB-0035` by id and its exact title.
- **15 domains**, evenly distributed (12 records each): Software Development, Java
  Backend, Python Backend, Frontend Development, Full Stack Development, Data
  Science, Machine Learning, Generative AI / NLP, Data Analytics, Cloud Computing,
  DevOps, Cybersecurity, Database / SQL, Software Testing / QA, Mobile Development.
- **Work mode**: evenly split On-site/Hybrid/Remote (60 each).
- **Quality**: 0 duplicate ids, 0 duplicate content, 0 missing required fields, all
  180 records pass the existing `job_dataset_service._validate_records` checks.
- **Confirmed: no code path special-cases `employment_type == "Internship"`** for
  matching/scoring fairness — `job_matching.score_experience` and
  `skill_gap_service.assess_experience` are both driven entirely by the posting's
  own `experience_requirements` *text* (`"no prior"`, `"entry-level"`, a `"N+
  years"` pattern, etc.), never by the `employment_type` field. This was the single
  most important audit finding: it meant the matching/skill-gap algorithms already
  treat any forgiving-experience posting fairly, for any type, with no code change.

## 2. Files referencing the dataset (rename risk assessment)

A repo-wide search found the dataset filename referenced in exactly one Python file
(`app/services/job_dataset_service.py`) plus its own `data/internships/README.md` —
confirming a rename was low-risk. `internship_jobs.faiss`/`internship_jobs_metadata.json`
(the FAISS index/metadata filenames) are referenced in `job_vector_store.py` and
`docs/MILESTONE_2_2.md`; these were **kept unchanged** (pure internal artifact names
with no user-facing meaning — renaming them would add risk for zero benefit).

## 3. Domain model decision: widen `employment_type`, no parallel `opportunity_type` field

The spec's suggested `opportunity_type` field (internship / entry_level_job /
graduate_role / trainee / apprenticeship) would have exactly duplicated what
`employment_type` already represented for the original two-value dataset. Per the
explicit instruction not to create a parallel duplicate concept when the existing
field already serves the purpose, **`employment_type`'s `Literal` was widened** from
`["Internship", "Entry Level"]` to `["Internship", "Entry Level", "Graduate Role",
"Trainee", "Apprenticeship"]` (`app/schemas/job_posting.py`, `job_posting_schema.json`
bumped to `schema_version: "1.1"`) — the single field this project already used as
its "opportunity type" axis now just has three more values. No new field, no new
column, no parallel model. There is no `Job`/`CareerOpportunity` SQL table at all in
this project — every job posting lives only in the JSON dataset + FAISS index; the
database only ever stores a loose `job_id: str` reference (in `SkillGap`,
`ApplicationCustomization`, `InterviewPreparation`, `Conversation`) — so **no
database migration was needed or performed**.

## 4. Final dataset composition

`backend/data/internships/career_opportunities_320.json` (schema_version 1.1) — the
180 original records unchanged, plus 140 newly generated records:

| Type | Count | Share |
| --- | --- | --- |
| Internship | 170 (150 original + 20 new) | 53% |
| Entry Level | 80 (30 original + 50 new) | 25% |
| Graduate Role | 45 (new) | 14% |
| Trainee | 15 (new) | 5% |
| Apprenticeship | 10 (new) | 3% |
| **Total** | **320** | |

Domains remain the same 15 (no new domain strings introduced, to avoid fragmenting
the existing taxonomy), now 21-22 records each. Locations/work-modes follow the same
distribution style as the original 180. New companies: 28 new fictional companies
(consistent naming style with the original 24) plus ~35% of new records reuse an
existing company (realistic — a company posts both internships and full-time roles).

**Data quality, explicitly checked** (not just asserted): zero duplicate `job_id`s,
zero duplicate `raw_text`, zero missing required fields (all pass the existing
`job_dataset_service._validate_records`), zero senior/lead/principal/staff/manager
wording anywhere in any title or description (`grep`-verified), zero `"N+ years"`
experience requirements among the 140 new records (all use the same forgiving,
dataset-established "no prior professional experience required" phrasing family,
so M2/M3.1's existing forgiving-experience logic treats them fairly with no code
change). Every new record's `job_title` is genuinely distinct per type — a Graduate
Role is titled "Graduate {X} Engineer", a Trainee "{X} Engineering Trainee", an
Apprenticeship "{X} Apprentice" — never a mechanical `employment_type` label swap on
an unchanged "...Intern" title (the exact quality issue found in the original 30
"Entry Level" records, deliberately not repeated for the new ones).

The generation script itself was a one-off (run in a scratch location, not
committed) that reused the *exact same* skill/responsibility/qualification
vocabulary already present in the real dataset per domain (extracted directly from
existing records), so new records read as authentic continuations of the existing
corpus rather than differently-styled additions.

## 5. Semantic index rebuild

`scripts/build_job_vector_index.py` was rerun against the new 320-record dataset:
320 jobs → 960 chunks (3 per job: overview/requirements/responsibilities, unchanged
chunking logic) → 960 vectors indexed. `chunk_job_postings` already includes
`employment_type` in every chunk's context and its `overview` chunk text ("...
Employment type: {type}. Description: ...") — this was already generic, so the new
`Graduate Role`/`Trainee`/`Apprenticeship` values flow through embedding with zero
code changes.

## 6. Search evaluation

Ten evaluation queries run against the rebuilt index (see the live validation
section for full output): `"Python machine learning internship"`, `"entry level
backend developer"`, `"graduate data analyst"`, `"junior Java developer"`,
`"frontend trainee"`, `"remote software internship"`, `"entry level SQL
developer"`, `"machine learning fresher"`, `"DevOps trainee"`, `"cybersecurity
internship"`. Every query's top results were semantically appropriate to the
requested type — e.g. `"graduate data analyst"` surfaced the real "Graduate Data
Analytics Engineer" record at rank 2; `"DevOps trainee"` surfaced the real "DevOps
Engineering Trainee" record at rank 1; `"junior Java developer"` surfaced three real
"Junior Java Backend Developer" (`Entry Level`) records in the top 3 — all with zero
changes to `embedding_service.py`/`job_search_service.py`.

## 7. Milestone-by-milestone impact

- **M2 (matching + retrieval)**: **zero code changes.** `job_matching.py`'s
  `score_experience` and `job_search_service.py`'s semantic search are both already
  type-agnostic (driven by real requirement text and embedded chunk text,
  respectively). `JobMatchResult`/`JobSearchResult` already carry `employment_type`
  end-to-end.
- **M3.1 (skill gap)**: **zero scoring-logic changes.** `assess_experience` is
  identically text-driven. Two user-facing strings generalized: `_get_job`'s
  `"Internship not found."` → `"Job posting not found."`
  (`skill_gap_service.py`), and the persisted-analysis 404 message
  `"No skill gap analysis found for this internship yet."` → `"...for this
  opportunity yet."` (`api/skill_gap.py`).
- **M3.2 (customization)**: **zero generation-logic changes.** The cover-letter
  opening (`cover_letter_service.py`) already read `"I am writing to express my
  interest in the {job.job_title} position at {job.company}"` — dynamically using
  the real title, never hardcoding "internship" — confirmed both by code audit and
  live validation (a real Gemini-generated cover letter for `JOB-0254` correctly
  opened *"...interest in the Graduate Python Backend Engineer position..."*). The
  `_get_job` 404 message generalized the same way as M3.1's.
- **M3.3 (interview prep)**: **zero question-generation-logic changes.** The
  `_get_job` 404 message generalized. Two HR-question-bank guidance strings that
  said "Most internships involve..."/"Internships often require..." were
  generalized to "Most early-career roles..."/"Early-career roles often..." (these
  are shown for every opportunity type, so the original wording was subtly
  inaccurate for a graduate/trainee candidate). Live-verified: a real Gemini-
  generated interview-preparation summary for `JOB-0254` correctly read
  *"Interview preparation for the Graduate Python Backend Engineer role at
  Driftstone Labs..."*.
- **M3.4 (assistant)**: the most user-facing-string-heavy milestone, since its
  response templates are hand-written English. Generalized: all follow-up/error
  messages (`"internship"` → `"opportunity"` in `assistant_service.py`), the
  `JOB_DISCOVERY` result message and its `facts` payload (now includes
  `opportunity_type` per match, and the message shows each match's type inline —
  `"FastAPI Intern at QuantumLeaf Technologies (Entry Level) — 66% match"`),
  `assistant_handlers.py`'s remaining internship-specific strings, the LLM system
  prompt's framing sentence, and `assistant_intent.py`'s `_DISCOVERY_KEYWORDS`
  (expanded with `"entry level jobs"`, `"graduate roles"`, `"trainee programs"`,
  `"apprenticeship"`, etc., and `_MATCH_EXPLANATION_KEYWORDS`' detection widened to
  catch `"why does JOB-0035 fit me?"`-style explicit-id phrasing, not just
  `"this role"`). `handle_job_comparison` was extended to explicitly state each
  side's **Type** and **Experience Expectations** as its own compared lines (the
  spec's explicit ask), and the LLM system prompt gained a rule: never change or
  assume an opportunity's type, and never call something an "internship" unless
  `facts` says it is one. Live-verified: asking *"Which graduate roles fit me?"*
  correctly singled out the one `Graduate Role` result among five real matches by
  reading the new `opportunity_type` fact field; comparing an `Internship` against
  a `Graduate Role` produced a purely factual `"Type: Internship vs Graduate
  Role."` line with no "better" language.

## 8. Frontend terminology

Audited every user-facing string in `App.tsx` containing "internship". Left
unchanged: every reference to the student's own resume **`internships`** section
(`structured_resume.data.internships`, `tailored_resume.internships`) — a real,
distinct resume category unrelated to the target opportunity's type, changing this
would be a false generalization, not a correct one. Generalized: `CareersView`'s
heading/placeholder/empty-states ("Search internships" → "Search opportunities"),
`SkillsView`'s lede/notices ("the internship you selected" → "the opportunity you
selected"), `CustomizeView`/`InterviewPrepView`'s empty-state copy and error
messages, the Career Assistant's context indicator and starter prompt. **New**: an
`.opportunity-type-chip` badge (existing `--amber`/`--pale-amber` palette, no new
colors) now shows the real `employment_type` on every job-search-result card,
every recommended-match card, and the Job Details page header — directly
satisfying the "cards should show opportunity type" requirement. `PageHeading`'s
`lede` prop was widened from `string` to `React.ReactNode` to allow the Job Details
page to render the badge inline next to the company/domain line (a minimal, additive
type change — every other caller still passes a plain string, which is valid
`ReactNode`).

Nav labels needed **no changes** — "Career Recommendations" and "AI Career
Assistant" were already generic (set during M2/M3.4's own initial builds), not
"Internship Recommendations".

## 9. Backward compatibility

- All 180 original records are byte-for-byte unchanged (verified: the generation
  script only *appends* new records; a diff of the first 180 array entries between
  the old and new file is empty).
- `JOB-0001` through `JOB-0180` (and specifically `JOB-0035`, referenced throughout
  the M3.2/M3.3/M3.4 test suites and every prior live-validation session) resolve
  identically — confirmed by `test_existing_internship_ids_still_resolve`.
- Every persisted `SkillGap`/`ApplicationCustomization`/`InterviewPreparation`/
  `Conversation` row from before this change references a `job_id` that still
  resolves to the identical posting content, so no historical record is silently
  invalidated. The existing staleness mechanism (each milestone's own `stale`
  computation, driven by `source_resume_updated_at`/`structured.updated_at`) is
  untouched and continues to work exactly as before — dataset expansion doesn't
  change a student's *resume*, so it cannot make an existing analysis newly stale.
- API routes are unchanged (`/api/jobs/...`, `/api/resumes/{id}/skill-gap`, etc.) —
  "jobs" remains the internal resource name throughout, per the explicit
  instruction to avoid a duplicate-route rename.

## 10. Tests

`backend/tests/test_career_opportunity_generalization.py` (14 new tests): canonical
dataset has all 5 types; search retrieves and preserves type across internship/
entry-level/graduate/trainee queries; M2 matching scoring works correctly (and
fairly) for a Graduate Role; M3.1 skill gap works for a Graduate Role; M3.2
customization for a Graduate Role never says "internship"; M3.3 interview prep for
a Graduate Role never says "internship"; the assistant's intent detection
understands internship/entry-level/graduate/trainee phrasing equally; the assistant
factually compares an Internship against an Entry-Level job (states `Type:`
explicitly, no "better" language); existing internship ids still resolve; FAISS
vector count matches dataset chunk count (960 = 320 × 3); ownership/persistence is
unchanged for a non-internship opportunity.

Two pre-existing tests updated for the new dataset size (a hardcoded count each,
not a behavior change): `test_job_dataset_service.py` (180 → 320),
`test_job_chunking.py` (540 → 960 chunks).

**Full regression**: `pytest -q` — **309 passed** (295 prior + 14 new), zero
failures beyond the two expected hardcoded-count updates above, which were fixed
before this count. `npm run build` / `npm run lint` — clean (0 TypeScript errors, 0
new lint issues).

## 11. Live E2E validation (2026-09-24)

Performed against the same real test account/resume/Gemini configuration used in
M3.3/M3.4's own live validation, against the freshly rebuilt 320-record dataset and
FAISS index:

- **Scenario — search across types**: searching `"graduate data analyst"` on the
  Career Recommendations page returned a real mix of Internship/Graduate Role/Entry
  Level results, each showing its own `opportunity-type-chip` badge (e.g. "Graduate
  Data Analytics Engineer" tagged **GRADUATE ROLE** at rank 2, 72% relevance).
- **Scenario C — Graduate role, full flow**: Job Details for `JOB-0254` ("Graduate
  Python Backend Engineer" at Driftstone Labs) correctly showed a **GRADUATE ROLE**
  badge and a description with zero internship wording → Analyze Skill Gaps
  correctly labeled **"SELECTED OPPORTUNITY"** (not "Selected Internship"), 79%
  readiness, 4/4 required skills matched → Customize Application generated a real
  Gemini ("AI Enhanced") cover letter opening *"I am writing to express my strong
  interest in the Graduate Python Backend Engineer position at Driftstone Labs"*
  (the student's own real past internship experience is still accurately mentioned
  later in the letter — correct, since that part is a true fact about the
  candidate, not a mislabeling of the target role) → Prepare for Interview
  generated a real Gemini interview preparation correctly titled "Preparing for
  Graduate Python Backend Engineer", with a summary reading *"Interview preparation
  for the Graduate Python Backend Engineer role at Driftstone Labs..."*.
- **Scenario D — mixed comparison via the assistant**: *"Which graduate roles fit
  me?"* correctly singled out the one real Graduate Role among five matches
  (*"your top graduate role match is the Graduate Python Backend Engineer at
  Driftstone Labs (Graduate Role), which has a 66% match..."*) — the LLM correctly
  used the new `opportunity_type` fact field to answer the type-specific question,
  an emergent benefit of exposing that field in `facts`. *"Compare JOB-0001 and
  JOB-0254"* (a real Internship vs. a real Graduate Role) produced a fully factual
  comparison — `"Type: Internship vs Graduate Role."`, required/preferred skills,
  experience expectations, and independently-computed readiness (59% vs. 79%) for
  each — with no "better"/evaluative language anywhere in the AI-synthesized text.
- Conversation context correctly carried the newly-established `JOB-0001` as the
  active opportunity into the next turn without being asked to repeat it, exactly
  matching M3.4's existing multi-turn behavior.
- Existing prior conversations (from the M3.3/M3.4 live-validation sessions,
  referencing the legacy `JOB-0035`) remained listed and intact in the sidebar
  throughout, confirming no persisted conversation data was disturbed.

## 12. Regression status

`pytest -q`: **309 passed**, 0 failed. `npm run build`: clean. `npm run lint`: clean
(1 pre-existing, unrelated warning in `ProfileView`, noted in the M3.3/M3.4 docs).
M1 (auth/resume), M2 (matching/search), M3.1 (skill gap), M3.2 (customization), M3.3
(interview prep), and M3.4 (assistant) all confirmed still functional, both via the
automated suite and live browser validation.

## 13. Known limitations

- **The 30 legacy "Entry Level" records still have a job title that says "...Intern"**
  (e.g. `JOB-0035`, "FastAPI Intern"). This is a pre-existing data quirk from the
  original M2.1 build, documented here rather than silently corrected — the
  `employment_type` field itself is and always was correctly "Entry Level" for
  these records, but the title text wasn't regenerated to match at the time. Fixing
  it now would change `job_title` text that M3.2/M3.3 generated content and prior
  live-validation sessions already reference by exact string; left unchanged per
  the explicit backward-compatibility requirement.
- **No UI filter controls for opportunity type/domain/location/work-mode** were
  added — the spec explicitly said this is optional ("if architecture allows") and
  that search must work without filters regardless; the type badge on every card
  and the Job Details page already surfaces the type visually, and free-text
  semantic search already favors the right type for a type-specific query (e.g.
  "graduate data analyst" surfaces Graduate Role results near the top) without
  requiring an explicit filter control. Adding filter UI remains a reasonable
  future enhancement, not a functional gap.
- **`employment_type` remains the single opportunity-type axis** — there is no
  separate, more granular taxonomy (e.g. distinguishing "government trainee
  program" from "corporate trainee program"). This matches the spec's own five-
  value target list exactly and avoids over-engineering a taxonomy the dataset
  doesn't need yet.

## 14. Is the generalized system safe to freeze?

**Yes.** Every definition-of-done criterion is met: the canonical dataset contains
all 5 opportunity types in meaningful quantity (320 records, 53/25/14/5/3% split);
internship data is 100% preserved unchanged; semantic search and FAISS retrieval
work correctly across types with a rebuilt, count-matched index; M2/M3.1/M3.2/M3.3
required zero business-logic changes and are confirmed working for every type, both
by automated test and live E2E validation; M3.4 understands and factually compares
across types; UI terminology no longer implies internship-only; existing internship
ids/flows/persisted records are all still valid; no mock runtime data was
introduced anywhere (every new record lives in the canonical dataset file, loaded
through the real retrieval pipeline like every other record — never hardcoded into
frontend or backend runtime logic); the full test suite and live validation both
pass cleanly.
