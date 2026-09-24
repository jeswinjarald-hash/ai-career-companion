# Milestone 3.3 — Interview Preparation Agent

Generates personalized, categorized interview preparation — questions, per-question
preparation guidance, and a prioritized revision plan — for a selected internship,
grounded in the student's real resume/profile, the real job posting, and Milestone
3.1's own skill gap analysis (reused, never re-scored). Follows the exact same
architecture Milestone 3.2 established: a **deterministic baseline that is always
computed in full**, with an **optional grounded LLM refinement layer** on top that can
only reword existing questions/guidance — never add, remove, reclassify, or invent one.

## Flow

```
Selected job (M2 dataset) + structured resume/profile (M1) + M3.1 skill gap analysis
(reused via analyze_skill_gap, not re-scored) + best-effort M2 match (optional context)
        v
Evidence builder             (app.services.customization_evidence.build_evidence_records,
                               reused directly from M3.2 — not duplicated)
        v
Interview context assembly   (app/services/interview_evidence.py)
  - supported/partial skill terms taken directly from M3.1's own strengths/gaps
  - projects ranked by job relevance (reuses M3.2's relevance_score)
        v
Deterministic question generation + revision plan   <- always computed, in full
(app/services/interview_question_service.py)
        v
Grounded LLM refinement, if a provider is configured (app/services/interview_llm.py)
  -> structured JSON output (same question count/index/category/difficulty)
  -> validated (category-aware fabrication checks + evidence_id existence)
  -> repair once if invalid
  -> merged onto the baseline if valid, else the baseline is used unchanged
        v
Category-aware fabrication validator runs again, as a final pass, over whichever
text is actually being shipped (app.services.customization_validator)
        v
Persisted, versioned InterviewPreparation (incl. GenerationMetadata + evidence)
        v
Frontend: categorized, expandable question cards + revision plan + optional
per-question mock-interview practice (stateless answer evaluation)
```

## Reused from Milestone 1 / 2 / 3.1 / 3.2 (not rebuilt)

- `app.services.customization_evidence.build_evidence_records` — the exact same
  `EvidenceRecord`/`evidence_id` provenance scheme M3.2 established.
- `app.services.customization_evidence.relevance_score` — the same project-ranking
  heuristic M3.2 uses, so the "most relevant project" is consistent across milestones.
- `app.services.skill_gap_service.analyze_skill_gap` — M3.1's full analysis
  (strengths, critical/partial/preferred/experience/qualification gaps) is called
  directly and never re-derived; this also persists its own `SkillGap` row as a side
  effect, matching M3.1's own upsert behavior.
- `app.services.job_matching.match_jobs_for_resume` / `normalize_term` — a
  best-effort M2 match is fetched for optional context; a miss (the selected job not
  appearing in the top-20 retrieval results) is handled the same way the existing Job
  Details page already handles it — it's omitted, not an error.
- `app.services.job_dataset_service.load_job_postings` — the real job posting.
- `app.services.llm_provider` (`LLMProvider`, `NullLLMProvider`,
  `OpenAICompatibleProvider`, `get_llm_provider`) — the exact M3.2 provider
  abstraction, zero new code.
- `app.services.customization_validator.check_fabrication` — M3.2's fabrication
  validator, extended (not forked) with a new narrower function (see below).
- Auth/ownership: `require_current_user`, `get_owned_resume`.
- Persistence pattern: a new model with a single JSON `data` blob column plus typed
  query columns, the same convention as `SkillGap`/`ApplicationCustomization`.
- Frontend: existing CSS classes and the existing typed-fetch service pattern
  (`src/services/*.ts`), and `ProvenanceDetails`/`GENERATION_LABEL`/`GENERATION_TONE`
  are reused directly from `App.tsx`, not reimplemented.

## Question categories and structure

Every `InterviewQuestion` has the same shape regardless of category or generation
path:

```json
{
  "question": "...",
  "category": "technical | resume | project | role | hr | skill_gap",
  "difficulty": "easy | medium | hard",
  "why_asked": "...",
  "what_interviewer_is_testing": "...",
  "preparation_guidance": "...",
  "topics_to_review": ["..."],
  "source_requirements": ["..."],
  "source_evidence_ids": ["EV-003"]
}
```

- **Technical** (`interview_question_service._technical_questions`) — one question
  per required/preferred job skill. If the skill is demonstrated *and* a matching
  project/experience evidence record exists, the question asks the student to explain
  their actual use of it ("Explain how you used FastAPI in \"Career Companion API\":
  ..."), citing that evidence's `evidence_id`. If the skill is required but not
  demonstrated with matching evidence, or is a preferred/gap skill, the question is
  purely conceptual/scenario-based (curated templates per technology family in
  `_TOPIC_QUESTIONS`, covering Docker/Kubernetes, cloud platforms, backend
  frameworks, frontend frameworks, ML libraries, databases, Git/CI-CD, REST API
  design) and never phrased as if the student already has hands-on experience.
  Required-and-demonstrated skills also get a second, harder scenario/debugging
  question. This directly implements the spec's own example: *"Explain how you used
  FastAPI in your AI Career Companion project"* is allowed; *"Tell me about your AWS
  deployment experience"* is never generated unless AWS evidence actually exists.
- **Resume-based** (`_resume_questions`) — one question per education/certification/
  achievement evidence record (capped at 6), each citing that record's own
  `evidence_id` — never a generic, ungrounded question.
- **Project-based** (`_project_questions`) — for the top 3 relevance-ranked projects,
  five questions each (architecture, technology choices, challenges, trade-offs,
  testing/debugging), all citing the project's own evidence and naming it by its real
  title — never inventing project details not present in the resume.
- **Role-specific** (`_role_questions`) — one question per real job responsibility
  (`job.responsibilities`, capped at 5), quoting the responsibility text itself in
  `source_requirements` so the question is provably tied to the actual posting.
- **HR/behavioral** (`_HR_QUESTION_BANK`) — six fixed, common student/intern
  questions (tell me about yourself, why this role, teamwork, a challenge faced,
  learning a new technology, strengths/weaknesses) with generic preparation guidance
  that does not require or invent specific resume evidence.
- **Skill-gap-focused** (`_skill_gap_questions`) — one question per critical/partial
  gap (`difficulty: "medium"`) and per preferred gap (`difficulty: "easy"`, capped at
  8 total), explicitly and honestly labeled as a gap: *"Your target role prefers
  Docker, but your resume does not show hands-on experience with it. How would you
  prepare to answer a question about Docker in this interview?"* — phrasing is
  templated to always state the gap ("does not show hands-on experience with" /
  "shows only partial/related evidence for") rather than ever implying the skill is
  already demonstrated.

`build_revision_plan` produces `RevisionItem`s (`priority: "high"|"medium"|"low"`)
from M3.1's own gaps — critical gaps first (`high`), then partial gaps and
experience gaps (`medium`), then preferred gaps (`low`), then the top 2 relevance-
ranked projects (`medium`, "review before the interview so you can speak fluently") —
sorted so `high` always precedes `medium` precedes `low`. No study duration is ever
invented; `estimated_focus` is a qualitative phrase ("Review before the interview so
you can speak fluently", "Lower priority — worth a light review if time allows"), not
a fabricated number of hours.

## Grounding: a category-aware fabrication check (the key architectural decision)

M3.2's `check_fabrication(text, unsupported_terms)` treats *any* mention of an
unsupported job keyword as an implied candidate claim — correct for a resume/cover
letter, where every sentence describes the candidate. That rule is **wrong** for
M3.3's `technical`/`role`/`skill_gap` categories, whose entire purpose is to
legitimately discuss a real job requirement or an explicitly-named skill gap by name
(the spec's own example above). Applying the unrestricted M3.2 check here was found,
during development, to incorrectly strip every conceptual Docker/Agile question as
"fabrication".

The fix, added without changing M3.2's behavior at all:

- `customization_validator.check_fabrication_patterns(sentence)` — a new function
  extracted from the metric/leadership/years-of-experience half of
  `check_fabrication`, **without** the unsupported-keyword check.
  `check_fabrication` itself now delegates to it (`unsupported_hit or
  check_fabrication_patterns(sentence)`), so M3.2's existing behavior and tests are
  byte-for-byte unchanged.
- `interview_prep_service.py`'s final validation pass is category-aware:
  `technical`/`role`/`skill_gap` questions are checked only with
  `check_fabrication_patterns` (an invented metric/leadership/years claim is still
  always rejected — mentioning a real gap skill by name is not); `resume`/`project`/
  `hr` questions get the full `check_fabrication` (including the keyword check) as a
  stricter safety net, since those categories only ever discuss the candidate's own
  claims.
- `interview_llm.py`'s `validate_llm_response` applies the identical distinction to
  the LLM's refined output, looking up each response question's category from the
  original (pre-refinement) question list; revision-plan entries always use the
  relaxed check, since a revision topic is inherently a skill/gap name to study.
- `interview_mock_service.py`'s answer-evaluation feedback also uses
  `check_fabrication_patterns` only (no keyword check), since feedback legitimately
  discusses whatever skill the student's own free-text answer mentions — including a
  gap skill a `skill_gap`-category question explicitly asked about.

## LLM refinement (`app/services/interview_llm.py`)

Mirrors `customization_llm.py` exactly. The system prompt states the rules
explicitly: the model may improve wording/clarity/tone of questions, guidance, the
summary, and the revision plan, and may emphasize `supported_skills`, but must never
invent a skill/technology/metric/experience/leadership/company/certification not in
`allowed_evidence`, must never phrase a question as presupposing hands-on experience
with an `unsupported_skills_do_not_use` entry, must cite `evidence_id`s for factual
claims, and — critically — must return the **exact same set of questions by index,
category, and difficulty**, refining wording only, never adding, removing, or
reclassifying one. `rewrite_with_llm` uses the identical repair-once-then-fallback
control flow as M3.2: call the provider, validate, one repair attempt on a validation
failure (skipped entirely on a provider-level failure like a timeout, since there's
no point retrying a dead connection), and a fallback to the deterministic baseline on
any remaining failure. `_apply_llm_refinement` merges a valid response onto the
baseline by index — only wording/evidence-citation fields change; `category`,
`difficulty`, and `source_requirements` always come from the deterministic pass, so
grounding never depends on the LLM getting classification right.

`GenerationMetadata` (`mode: "llm" | "deterministic_fallback"`, `provider`, `model`,
`repair_attempted`, `fallback_reason`) is persisted and surfaced as the same **"AI
Enhanced"** / **"Grounded Fallback"** badge M3.2 uses.

## Deterministic fallback

No LLM is required for a complete, usable result: every question the deterministic
generator produces already cites real `evidence_ids` or `source_requirements`, every
category is populated from real data (never a generic placeholder question), and the
revision plan is fully derived from M3.1's own gaps. An unconfigured, failing, or
misbehaving LLM provider always leaves this fully-grounded deterministic output in
place — the LLM is never a single point of failure.

## Persistence, versioning, staleness

New `interview_preparations` table (`app/models/career_state.py`,
`InterviewPreparation`): `user_id`, `resume_id`, `job_id`, `version`, `status`,
`source_resume_updated_at`, and a single JSON `data` column holding the job title/
company, preparation summary, questions, revision plan, the evidence records used
(so the frontend's "Supported by" provenance UI can resolve `source_evidence_ids` to
real text, the same pattern M3.2 uses), validation result, and generation metadata.
`UniqueConstraint(resume_id, job_id, version)`. Every "generate" or "regenerate" call
inserts a **new** version rather than overwriting a prior one — a student can compare
"FastAPI Intern — v1 · AI Enhanced" against "FastAPI Intern — v2 · Grounded Fallback"
side by side, and an older version is never silently mutated.

**Staleness**: computed at read time (`stale = source_resume_updated_at <
structured.updated_at`), the same pattern as M3.1/M3.2 — never silently reused if the
resume has changed since generation.

**Parser-warning gate**: if `StructuredResume.data.parser_warnings` is non-empty, a
fixed-string notice is attached to `validation.warnings` and surfaced in the
frontend, so a student doesn't unknowingly trust resume-based questions generated
from a resume the parser itself flagged as uncertain. If the evidence layer produces
fewer than 3 records at all, generation is refused with `409`.

## API

```
POST   /api/resumes/{resume_id}/interview-preparations?job_id=...
GET    /api/resumes/{resume_id}/interview-preparations[?job_id=...]
GET    /api/resumes/{resume_id}/interview-preparations/{id}
POST   /api/resumes/{resume_id}/interview-preparations/{id}/regenerate
POST   /api/resumes/{resume_id}/interview-preparations/{id}/mock-answer
```

Every endpoint requires authentication and verifies `get_owned_resume(db, resume_id,
current_user.id)` before touching a record, plus `record.resume_id == resume_id` —
a user can never read, regenerate, or submit a mock answer against another user's
interview preparation (`404`, matching the rest of the codebase's convention).

## Mock interview (implemented)

A stateless, per-question practice loop — no persisted answer/session history; each
submission is evaluated independently against the question it answers.
`POST .../mock-answer` takes `{question_index, answer}` and returns a
`MockAnswerEvaluation`: `strengths`, `improvements`, `missing_points`,
`suggested_structure`, and `grounded_feedback`, plus the same `GenerationMetadata`/
badge convention. `app/services/interview_mock_service.py` provides a deterministic
heuristic baseline (answer length, whether the question's own `topics_to_review` are
mentioned, a STAR-structure suggestion for HR questions vs. a context/approach/
outcome/reflection structure for technical/project ones) and an optional LLM path
that evaluates only what the student actually wrote — it is explicitly instructed
never to infer personality, intelligence, or "fit", never to assign a numeric score,
and never to introduce a factual correction unsupported by the role/question context.
**No arbitrary numeric score is ever produced** — feedback is qualitative only, per
the spec's explicit requirement, since no deterministic, documented scoring rubric
exists for this milestone.

## Frontend

`src/services/interviewPrepService.ts` follows the existing typed-fetch pattern.
Entry points: a **"Prepare for Interview"** button on the Job Details page, the
Skill Gap Analysis page, and the Customize Application page — the already-selected
job/resume carries over automatically.

The Interview Preparation page shows: a version switcher (`v2 · Grounded Fallback`,
`v1 · AI Enhanced` — regenerate always creates a new version); the **"AI Enhanced" /
"Grounded Fallback"** badge with the same three-state explanatory line M3.2 uses; a
grounding-check banner; a preparation summary; each category (Technical,
Resume-based, Project-based, Role-specific, HR/Behavioral, Skill-gap-focused) as its
own section with expandable `<details>` question cards — collapsed to the difficulty
badge and question text, expanding to why it's asked, what the interviewer is
testing, how to prepare, topics to review, the source job requirement(s), and a
collapsible "Supported by" evidence section (reusing `ProvenanceDetails` directly);
a prioritized revision plan section; and, per question, an inline **"Practice this
question"** control that reveals a textarea and submits to the mock-answer endpoint,
rendering the same AI Enhanced/Grounded Fallback badge plus strengths/improvements/
missing points/suggested structure/grounded feedback — no numeric score anywhere in
the UI.

## Tests

- `backend/tests/test_interview_prep_service.py` (13 tests) — technical questions
  grounded in real job requirements (source_requirements always a subset of the
  job's actual skill set); resume questions reference real evidence; project
  questions reference real project names and never invent one; missing skills are
  never phrased as if demonstrated; skill-gap questions are correctly labeled and
  reference the correct requirement; unrelated technologies (Kubernetes, React,
  PyTorch, TensorFlow, MongoDB, Azure — none present in the test resume/job) never
  appear anywhere in the output; revision priorities follow M3.1's own gap
  ordering; malformed LLM output triggers exactly one repair attempt then falls
  back; a provider timeout falls back **without** wasting a repair call; a valid
  LLM response yields `generation.mode == "llm"`; a hallucinated LLM claim ("5
  years of professional experience with AWS") is rejected and falls back; the
  original `Resume`/`StructuredResume` are never mutated; staleness detection
  works. Every LLM-path test injects a fake provider — no live Gemini calls.
- `backend/tests/test_interview_prep_api.py` (9 tests) — authentication required
  on every endpoint; `409` when no structured resume exists yet; `404` for an
  unknown resume or unknown job; cross-user ownership isolation (a second user
  cannot read, regenerate, or submit a mock answer against another user's
  preparation); regenerate creates a new version while the prior one stays
  readable unchanged; generating again for the same job also creates a new
  version; the full response shape (all 6 categories present, every question has
  guidance) is validated end-to-end through the API; the mock-answer endpoint
  returns a well-formed, score-free evaluation; an out-of-range `question_index`
  returns `404`. `get_llm_provider` is monkeypatched to `NullLLMProvider` for this
  file specifically — `get_settings()` is process-wide `lru_cache`d and this
  repository's real `backend/.env` carries a live Gemini key for manual
  validation, so without this override these API-level tests would make real,
  billed calls (confirmed: 173s -> 27s for the same 9 tests after adding the
  override, and both call sites — `app.services.interview_prep_service` and
  `app.api.interview_prep` — had to be patched individually, since a `from ...
  import` binds its own local name independent of the origin module).

Full backend regression (`pytest -q`, 253 tests across M1/M2/M3.1/M3.2/M3.3):
**253 passed**. `npm run build` and `npm run lint`: clean (0 TypeScript errors, 0
new lint errors — the sole lint warning is pre-existing in `ProfileView`, unrelated
to this milestone).

## Live E2E validation and manual grounding audit (2026-09-24)

Performed against a freshly created test account and a real uploaded resume
("Jordan Rivera" — skills Python/FastAPI/SQL/Git/REST APIs, one backend project
citing FastAPI/PostgreSQL/JWT authentication/pytest, one backend internship at Acme
Software, one Coursera certification) and the real `JOB-0035` posting ("FastAPI
Intern" at QuantumLeaf Technologies; required Python/SQL/REST APIs/Git, preferred
FastAPI/Flask/PostgreSQL/Docker/Agile), through the full browser UI:

login -> resume upload/processing -> Job Details (`/jobs/JOB-0035`) -> **"Prepare for
Interview"** -> Generate -> full result inspected -> evidence provenance expanded ->
mock interview answered -> provider-unavailable fallback tested -> version switching
verified.

- **Real Gemini call succeeded**: the badge showed *"AI Enhanced — Refined by
  openai_compatible (gemini-flash-lite-latest), validated against your evidence."*,
  and the grounding-check banner passed with zero removed claims.
- All 6 categories were populated from a single real generation: 13 technical, 2
  resume-based, 5 project-based, 5 role-specific, 6 HR, 3 skill-gap questions (34
  total).
- **Manual grounding audit — technical (5 of 13 checked)**: "Explain how you used
  Python in your backend internship and projects" (Python is required, resume shows
  it in both) &check;; "A Python module or API handler isn't behaving as expected...
  how would you start investigating?" (conceptual, no unsupported claim) &check;;
  "Explain how you used SQL in your experience at Acme Software... against
  PostgreSQL" (matches the resume's exact experience text) &check;; "Explain how you
  designed REST APIs in the Career Companion API project... how did you handle
  authentication?" (JWT authentication is literally in the project's raw text)
  &check;; "What problem does containerization solve, and how does Docker help...
  conceptually?" (Docker is an unmet preferred skill — correctly phrased as
  conceptual-only, never implying the student used Docker) &check;.
- **Manual grounding audit — resume/project (5+2 checked, all present)**: both
  resume-based questions traced to real evidence (the education entry, the Coursera
  certification); all 5 project-based questions named the real project
  ("Career Companion API") and asked only about its actual, resume-stated content
  (architecture, technology choices, challenges, refactoring, pytest testing — pytest
  is literally mentioned in the resume) — none invented a detail not present.
- **Manual grounding audit — revision plan (4 of 4 checked)**: the Career Companion
  API project (medium priority — real project, relevant to the project-based
  questions); Flask, Docker, Agile (all low priority, all M3.1 preferred gaps,
  each phrased as "not demonstrated" / "partial or related familiarity", never as
  something the student has). Priorities were correctly ordered medium before low
  (this student had zero critical/partial required-skill gaps, so no `high` items
  existed — consistent with meeting all 4 required skills).
- **Evidence provenance UI**: expanding "Supported by (3)" on a technical question
  correctly resolved `source_evidence_ids` to real, human-readable evidence —
  the Resume Skills Section entry, the Career Companion API project's full text, and
  the Acme Software experience entry — confirming the `evidence` list added to the
  `InterviewPreparation` API response (see below) resolves correctly end-to-end.
- **Mock interview, live**: answered a technical question ("Explain how you used
  Python...") with a real, evidence-grounded free-text answer. The real Gemini call
  returned genuinely evaluative, non-fabricated feedback: it credited the concrete
  Python/FastAPI/PostgreSQL/Acme Software/Career Companion API references, and
  correctly identified that the answer "completely misses the two prompts regarding
  your specific approach and what you would do differently now" — a real critique of
  what was and wasn't actually written, with a suggested STAR-adjacent structure and
  no numeric score.
- **Provider-unavailable -> Grounded Fallback, live**: `LLM_PROVIDER` was
  temporarily set to `none` in `backend/.env` and the backend restarted; clicking
  Regenerate produced a new version correctly tagged **"Grounded Fallback"** with
  the exact required message *"No LLM provider is configured — this is the
  deterministic, template-based version."*, a passed grounding check, and a fully
  populated result (13 technical / 6 HR / 5 project / 5 role / 3 skill-gap / 2
  resume questions) — the deterministic pipeline alone is already complete. The
  version switcher correctly preserved `v1 · AI Enhanced` alongside the new `v2 ·
  Grounded Fallback`, and clicking back to `v1` restored the original AI-refined
  content unchanged, confirming version immutability live. `.env` was then restored
  to the real Gemini configuration and the backend restarted again.
- **API key hygiene re-verified**: `git check-ignore -v backend/.env` confirmed it
  remains gitignored, and `git grep` for the key value found zero matches in tracked
  content, both before and after this session's `.env` edits.

**One schema addition made during this milestone's build, not originally listed in
the initial file plan**: the `InterviewPreparation` API response initially exposed
only `source_evidence_ids` per question with no way to resolve them to human-readable
text (unlike M3.2's `ApplicationCustomization.evidence`). Since the frontend spec
explicitly requires showing "Relevant evidence" per question card, an `evidence:
list[EvidenceRecord]` field (mirroring M3.2's exact pattern) was added to the
response schema and the service's persisted `data` payload. Covered by the existing
test suite (re-run clean, 22/22) and confirmed live via the "Supported by" UI above.

## Known limitations

- **Mock interview has no persisted session/history** — each answer is evaluated
  independently; there is no "interview session" record tying a sequence of answers
  together, per the spec's framing of this as an optional, stateless practice loop
  layered on top of the already-generated, already-persisted question set.
- **No numeric interview score, by design** — per the spec's explicit instruction
  ("no arbitrary scores unless a deterministic, documented rubric exists"), and no
  such rubric was defined for this milestone. Feedback is qualitative only
  (strengths/improvements/missing points/suggested structure/grounded feedback).
- **Best-effort M2 match is optional context only** — M2's retrieval is
  similarity-based over a `top_k`-capped result set, so the selected job is not
  guaranteed to appear even when it's a strong match; a miss is silently omitted
  from context rather than treated as an error, the same way the existing Job
  Details page already handles it.
- **Curated technical-question templates cover common technology families, not
  every possible job skill** — an uncurated skill (not in `_TOPIC_QUESTIONS`) falls
  back to a generic-but-still-grounded conceptual template
  (`_GENERIC_TEMPLATES`), naming the real skill, rather than a hardcoded per-skill
  question bank.
