# Milestone 3.2 — Resume & Cover Letter Customization Agent

Generates a role-specific tailored resume and cover letter from a student's existing
structured resume/profile and a selected internship. The pipeline is a **deterministic
baseline with an optional, grounded LLM rewrite layer on top**: the deterministic
pipeline (M2/M3.1's own convention — no LLM, every claim traceable) is always computed
in full first; when an LLM provider is configured, its JSON output is validated by the
same fabrication checks and, only if it passes, merged onto the baseline; an
unconfigured, failing, or misbehaving provider always leaves the fully-grounded
deterministic result in place. Nothing is ever generated freely, nothing is trusted
without a traceable source, and the LLM is never the single point of failure for
producing usable output.

## Grounding architecture: deterministic baseline + optional LLM layer

The milestone's own grounding rule is non-negotiable: every generated claim must be
traceable to real student evidence, and an unsupported job keyword must never be
inserted into a claim. The **deterministic baseline** makes this trivially provable —
a bullet's `tailored_text` is, by construction, the original text with only
whitespace/punctuation normalization, so it cannot contain an invented claim. This
baseline is *always* computed, on every request, regardless of whether an LLM is
configured — it is the fallback, not an afterthought.

The **LLM rewrite layer** (`app/services/llm_provider.py`, `app/services/
customization_llm.py`) is an enhancement applied on top of that baseline, never a
replacement it depends on:

1. The model is given a restricted, structured payload — the job, the supported/
   partial/unsupported skill classifications, the deterministic baseline summary, the
   exact bullets to rewrite, and a fixed `allowed_evidence` list with stable
   `evidence_id`s — never a free-form "rewrite my resume" prompt.
2. Its JSON response is validated: every cited `evidence_id`/`source_path` must exist
   in what was actually offered, and every piece of rewritten text is run through the
   *same* fabrication checks the deterministic pipeline already uses
   (`customization_validator.check_fabrication` — unsupported keywords, invented
   metrics, invented leadership/team-size claims, invented years of experience).
3. On a validation failure, **one** repair attempt is made (the model is shown exactly
   what was wrong and asked to fix it). A second failure, or any provider-level
   failure (timeout, network error, non-JSON response), falls back to the
   deterministic baseline — no infinite retries, no partial/broken output ever
   reaches the user.
4. `GenerationMetadata` (`mode: "llm" | "deterministic_fallback"`, `provider`,
   `model`, `repair_attempted`, `fallback_reason`) is persisted alongside every
   customization and surfaced in the UI as an **"AI Enhanced"** or **"Grounded
   Fallback"** badge — the student always knows which path produced what they're
   looking at.

## Flow

```
Original resume (M1) + structured profile + selected job (M2 dataset)
        +
M3.1 skill gap analysis is not required as an input (re-derives the same
grounded evidence directly), but its evidence-matching function is reused
        v
Evidence builder            (app/services/customization_evidence.py)
        v
Job keyword classification  (app/services/customization_keywords.py,
                              reuses skill_gap_evidence.match_requirement)
        v
Deterministic resume customization + cover letter   <- always computed, in full
(app/services/resume_customization_service.py, cover_letter_service.py)
        v
Grounded LLM rewrite, if a provider is configured  (app/services/customization_llm.py)
  -> structured JSON output
  -> validated (fabrication checks + evidence_id/source_path existence)
  -> repair once if invalid
  -> merged onto the baseline if valid, else the baseline is used unchanged
        v
Unsupported claim validator runs again, as a final pass, over whichever text is
actually being shipped (app/services/customization_validator.py)
        v
Persisted, versioned ApplicationCustomization (incl. GenerationMetadata)
        v
Frontend review/edit (incl. per-bullet editing + provenance)  ->  export (PDF/DOCX)
```

## Reused from Milestone 1 / 2 / 3.1 (not rebuilt)

- Structured resume shape (`StructuredResume.data`) and the M1 parser — read only,
  never mutated by this milestone.
- `app.services.job_matching.normalize_term` for consistent term canonicalization.
- `app.services.job_dataset_service.load_job_postings` for the selected job's full
  posting (required/preferred skills, responsibilities, qualifications).
- **`app.services.skill_gap_evidence.build_evidence_units` and `match_requirement`**
  — M3.1's exact demonstrated/partial/learning_only/missing matcher is reused
  directly for job-keyword classification (mapped to supported/partial/unsupported)
  rather than re-implemented, so the two milestones' skill-matching behavior can
  never silently diverge.
- Auth/ownership: `require_current_user`, `get_owned_resume`.
- Persistence pattern: a new model with a single JSON `data` blob column, the same
  convention as `StructuredResume`/`SkillGap`.
- Frontend: existing CSS classes (`.card`, `.comparison-card`, `.skill-chip`,
  `.warning-chip`, `.skill-status`, `.detail-actions`, ...) and the existing
  typed-fetch service pattern (`src/services/*.ts`).

## Claim provenance layer (`customization_evidence.py`)

`build_evidence_records(profile, structured_data)` returns a list of `EvidenceRecord`:

```json
{
  "evidence_id": "EV-003",
  "source_type": "project",
  "source_name": "AI Career Companion",
  "source_path": "structured_resume.projects[0].raw_text",
  "raw_text": "Built backend REST APIs using FastAPI and PostgreSQL...",
  "canonical_terms": ["ai career companion", "fastapi", "postgresql"],
  "confidence_type": "direct"
}
```

`source_path` is an indexed field path into the actual structured resume/profile —
every record can be traced back to the exact field it came from. Content sourced
from an "Areas Currently Learning"-style section gets `confidence_type:
"learning_only"` (never `"direct"`), mirroring M3.1's `learning_only` match type.

## Job keyword classification (`customization_keywords.py`)

Only `required_skills` and `preferred_skills` are classified (the job dataset's only
discrete, comparable keywords — free-text responsibilities/qualifications are
surfaced to the customizer through the evidence layer instead). Each keyword is
classified by calling M3.1's `match_requirement` against the same
`build_evidence_units` output:

| M3.1 match_type | M3.2 status |
| --- | --- |
| `demonstrated` | `supported` |
| `partial` | `partial` |
| `learning_only` | `partial` (worded conservatively, never "hands-on") |
| `missing` | `unsupported` |

`matched_evidence_ids` cross-references this milestone's own `EvidenceRecord`s (by
re-running the same term/related-term match against their `canonical_terms`/
`raw_text`), so the frontend can show *which* evidence backs a "supported" label.

## Resume customization (`resume_customization_service.py`)

- **Skills** — the original `structured_resume.skills` list is stable-sorted
  (supported first, then partial, then the rest, ties broken by original order).
  Nothing is ever added: `tailored_resume.skills` is always exactly the same set as
  the original list.
- **Projects/bullets** — ranked by a relevance score (`customization_evidence.
  relevance_score`: 2 points per supported keyword match in technologies/text, 1
  point per partial match), never dropped. Each project/bullet's `tailored_text`
  equals `original_text` after only whitespace/punctuation normalization — no
  paraphrasing — so `introduced_claims` is always `[]` and every word is
  byte-traceable to `source_path`. `job_keywords_used` lists which supported/partial
  keywords appear verbatim in that text (an annotation, not a rewrite).
- **Professional summary** — the one place a genuinely new sentence is composed, and
  it is built strictly from known fields: `profile.degree`/`specialization` (or the
  first education entry's raw text as a fallback) plus the top job-relevant
  *existing* skill names. `summary_sources` records exactly which fields were used.

## Cover letter (`cover_letter_service.py`)

Five to six template sentences: an opening naming the real job title/company (no
claim, empty `sources`), an education/interest line, a top-skills sentence, a
best-project citation (colon-cited verbatim, not spliced into an invented
continuation), an experience/internship citation if any exists, and a closing with
no factual claim. Every factual sentence's `sources` lists the `EvidenceRecord`
`source_path`(s) it was built from.

## Unsupported claim validator (`customization_validator.py`)

A second, independent pass over the *already-generated* summary and cover letter
text — not trusted just because it came from a template. Scans for:

- any keyword classified `unsupported` appearing verbatim in the text,
- an unverified numeric metric (`r"\d+%"`, "improved ... by ..."),
- an unverified leadership/team-size claim ("led a team", "team of N"),
- an unverified years-of-experience claim ("N years of ... experience").

A hit strips that sentence from the output, records it in `validation.
removed_claims`/`warnings`, and sets `status` to `validation_warning` — never
silently returned. In this deterministic pipeline the summary/cover letter are
composed only from known fields, so a hit here in practice indicates a template
bug, not routine behavior; it exists as defense-in-depth, and is unit-tested
directly (`test_customization_validator.py`) with deliberately fabricated input.

## LLM provider abstraction (`app/services/llm_provider.py`)

A small `LLMProvider` protocol (`generate_json(system_prompt, payload) -> dict`, raises
`LLMUnavailableError` on any failure) so the pipeline never depends on a vendor SDK:

- `NullLLMProvider` — used when `settings.llm_provider == "none"` (the default). Raises
  immediately; never pretends a model is configured.
- `OpenAICompatibleProvider` — speaks the OpenAI chat-completions wire format (JSON
  mode) over plain `httpx` (already a dependency, no new SDK). Works against OpenAI
  itself, Azure OpenAI's compatible surface, or a locally hosted server (Ollama, vLLM,
  LM Studio, ...) via `LLM_BASE_URL` — no code change needed to switch providers.
- `get_llm_provider(settings)` factory picks between them based on config.

New settings (`app/core/config.py`, `.env.example`): `LLM_PROVIDER` (`none` by
default), `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_TIMEOUT_SECONDS`. No secret
is ever logged, hardcoded, or persisted — `LLM_API_KEY` is read from the environment
only and never appears in the customization record's stored `GenerationMetadata`
(only the provider name and model identifier are persisted).

`generate_customization(..., llm_provider: LLMProvider | None = None)` accepts an
optional provider override, used by tests to inject a fake provider — no real
external LLM is ever called from the automated test suite.

## Grounded LLM rewrite (`app/services/customization_llm.py`)

`build_grounded_llm_input` constructs the restricted payload:

```json
{
  "job": {"title": "...", "company": "...", "domain": "...", "required_skills": [...], "preferred_skills": [...], "responsibilities": [...]},
  "supported_skills": ["Python", "FastAPI"],
  "partial_or_learning_skills": ["Docker"],
  "unsupported_skills_do_not_use": ["Agile"],
  "baseline_summary": "...",
  "bullets_to_rewrite": [{"source_path": "...", "kind": "project", "title": "...", "original_text": "..."}],
  "allowed_evidence": [{"evidence_id": "EV-003", "source_path": "...", "source_type": "project", "text": "...", "confidence": "direct"}]
}
```

The system prompt (in the same file) states the rules explicitly: the model may
reword/clarify/reorder/shorten/prioritize and may emphasize `supported_skills`, but
must never invent a skill, technology, tool, metric, year of experience, team size,
leadership role, company name, job title, date, certification, or achievement not
present in `allowed_evidence`, must never present an `unsupported_skills_do_not_use`
entry as something the candidate has, and must cite `evidence_id`(s) for every factual
claim. The required JSON response shape (`LLMRewriteResponse`): `summary` +
`summary_evidence_ids`, `bullets` (one per `source_path` in `bullets_to_rewrite`, each
with `rewritten_text` + `evidence_ids` + `job_keywords_used`), and
`cover_letter_paragraphs` (3–6, each with `text` + `evidence_ids`).

`validate_llm_response` checks: every cited `evidence_id` exists in the offered
`allowed_evidence`; every `bullets[].source_path` is one that was actually asked for
(and every asked-for one got a rewrite — no silent omissions); every piece of text
(summary, each bullet, each cover-letter paragraph) passes
`customization_validator.check_fabrication` — the exact same unsupported-keyword and
fabricated-metric/leadership/years-of-experience checks the deterministic pipeline's
own validator uses, not a separate, weaker check.

`rewrite_with_llm` orchestrates: call provider -> parse/validate -> if invalid, one
repair call (the model is shown its previous response and the specific violations) ->
re-validate -> if still invalid (or the provider itself failed/timed out, which skips
repair entirely — no point retrying a dead connection), return `None` with a
`fallback_reason`. `_apply_llm_rewrite` (in `resume_customization_service.py`) merges
a valid response onto the baseline: only `tailored_text`/`summary`/cover-letter text
and their cited evidence change — `original_text`, `source_path`, `technologies`, and
`relevance_rank` always come from the deterministic pass, so provenance and ranking
stay intact regardless of which path produced the wording.

The deterministic baseline also backfills its own `evidence_ids` (a bullet's evidence
*is* its own `EvidenceRecord`, same `source_path`) before the LLM step runs, so the
frontend's "Supported by" provenance UI has real data even with no LLM configured —
the LLM path simply overwrites these with its own (already-validated) citations for
whatever it actually rewrote.

## Parser-warning gate

If the source `StructuredResume.data.parser_warnings` is non-empty, a fixed-string
notice ("Resume structure contains parsing warnings. Review extracted profile before
customization.") is attached to `validation.warnings` (shown, not silently hidden).
If the evidence layer produces fewer than 3 records at all, generation is refused
with `409` rather than producing a materials from too little to be meaningfully
grounded.

## Persistence and versioning

New `application_customizations` table (`app/models/career_state.py`,
`ApplicationCustomization`): `user_id`, `resume_id`, `job_id`, `version`, `status`,
`source_resume_updated_at`, and a single JSON `data` column holding evidence,
keyword classification, the tailored resume, the cover letter (with provenance),
validation result, **generation metadata**, and user edits.
`UniqueConstraint(resume_id, job_id, version)`. A record written before this LLM-layer
upgrade has no `generation` key at all — read back with a synthesized
`deterministic_fallback` metadata (`_LEGACY_GENERATION_METADATA`) so old rows still
deserialize correctly.
The original `Resume`/`StructuredResume` rows are never written to by this
milestone — every "generate" or "regenerate" call inserts a **new** version rather
than overwriting a prior one, so a student can compare "FastAPI Intern — v1" against
"FastAPI Intern — v2" or a different job's customization side by side.

**Staleness**: computed at read time (`stale = source_resume_updated_at <
structured.updated_at`), the same pattern as M3.1 — never silently reused.

## API

```
POST   /api/resumes/{resume_id}/application-customizations?job_id=...
GET    /api/resumes/{resume_id}/application-customizations[?job_id=...]
GET    /api/resumes/{resume_id}/application-customizations/{id}
PATCH  /api/resumes/{resume_id}/application-customizations/{id}
POST   /api/resumes/{resume_id}/application-customizations/{id}/regenerate
GET    /api/resumes/{resume_id}/application-customizations/{id}/export?document=resume|cover_letter&format=pdf|docx
```

Every endpoint requires authentication and verifies `get_owned_resume(db, resume_id,
current_user.id)` before touching a customization row, and additionally checks
`customization.resume_id == resume_id` — a user can never read, edit, regenerate, or
export another user's customization (`404`, not `403`, matching the rest of this
codebase's ownership-check convention).

`PATCH` accepts `summary`, `cover_letter_text`, and/or `bullet_edits` (keyed by
`source_path`). Only fields the caller actually includes are applied and marked in
`user_edits.edited_fields` — a user-edited field is flagged as no longer an
AI-generated, evidence-verified claim (never silently re-validated as if it were
still grounded), per the requirement that user edits must be distinguishable from
generated content.

## Export (`customization_export_service.py`)

In-memory PDF (`reportlab`, new dependency) and DOCX (`python-docx`, already
installed but previously used only for *reading*) generation from an already
persisted, validated customization — never written to disk, never touching the
resume storage directory or the original uploaded file. Layout is a single column
with standard section headings and plain paragraph/bullet flowables only (no tables,
no images), so the text stays fully selectable and ATS-parseable.

## Frontend

`src/services/customizationService.ts` follows the existing typed-fetch pattern.
Entry points: a **"Customize Application"** button on the Job Details page (next to
"Analyze Skill Gaps") and on the Skill Gap Analysis page — the already-selected
job/resume carries over automatically, no manual ID re-entry anywhere.

The Customize Application page shows: a version switcher, each version tagged with
its generation mode (`v3 · AI Enhanced`, `v4 · Grounded Fallback` — regenerate always
creates a new version, never overwrites); an **"AI Enhanced" / "Grounded Fallback"**
badge with an explanatory line (naming the provider/model when LLM-generated;
*"AI enhancement unavailable or failed validation. A grounded fallback version is
shown."* when an LLM was attempted but failed; *"No LLM provider is configured..."*
when none was ever attempted — three distinct, honest states, never a generic
failure message); a grounding-check banner ("Grounding check passed" or "Grounding
warnings found" with the validator's warnings); a keyword alignment section
(supported / partially supported / unsupported chips, with an explicit note that
unsupported keywords are never added); original-vs-reordered skills; **projects and
experience/internship bullets each shown as an Original-vs-Tailored comparison**,
with a collapsible **"Supported by"** provenance section listing the evidence
source name and text behind that specific piece of text, and an inline editable
textarea for the bullet itself; an editable summary and cover letter (each showing a
"user edited" notice once touched, with its own provenance section); and PDF/DOCX
export buttons for both documents (fetched as a blob with the session cookie and
downloaded client-side, not a plain cross-origin link) — export always serves the
persisted, current version, including any saved user edits.

Loading/error states never leave the UI stuck: a `status === 'loading'` message shows
during generate/regenerate, and any failure (network, 409, validation) surfaces as an
`error-notice` with a real message, never a silent hang.

## Tests

- `backend/tests/test_customization_validator.py` — unit tests on the validator
  directly: fabricated metric rejection, fabricated leadership rejection, fabricated
  years-of-experience rejection, unsupported-keyword rejection, and the
  nothing-to-flag pass case.
- `backend/tests/test_customization_service.py` — evidence provenance completeness,
  supported/unsupported/learning-only keyword classification against a real job
  posting, project relevance ordering (a backend project ranks above an unrelated
  frontend project for a backend job), original-resume immutability, staleness
  detection, negative testing (a job's entirely-absent required technologies never
  appear anywhere in the output), and deterministic consistency across a
  regeneration.
- `backend/tests/test_customization_api.py` — authentication required on every
  endpoint, `404`/`409` error states, cross-user ownership isolation (a second user
  cannot read, edit, regenerate, or export another user's customization),
  versioning (regenerate/re-generate always adds a new version, never overwrites a
  prior one), user-edit persistence with the "user edited" distinction, and export
  returning valid PDF/DOCX for both documents.
- `backend/tests/test_customization_llm.py` — **no real external LLM is ever called**;
  every test injects a fake `LLMProvider`. Covers: a valid grounded rewrite is
  accepted and marks `generation.mode == "llm"`; a Docker-hallucination response is
  rejected and falls back; a fabricated 40% metric is rejected and falls back; a
  fabricated "led a team of 5" claim is rejected and falls back; an unknown
  `evidence_id` is rejected (repair attempted, then falls back); a malformed JSON
  shape triggers exactly one repair attempt then falls back; a provider timeout
  falls back **without** wasting a repair call on a dead connection; a repair that
  succeeds on the second attempt is accepted; the original `StructuredResume` is
  never mutated on the LLM path; ownership is still enforced; and versioning still
  works, all with the LLM path active.

## Live E2E validation and manual grounding audit (2026-09-23, M3.2 initial)

Performed against a real uploaded resume ("Alex Morgan" — skills Python/FastAPI/SQL/
Git/HTML/CSS, one backend project, one unrelated portfolio project, one internship,
a "Currently Learning: Docker, Kubernetes" section) and a real job posting
(`JOB-0035`, "FastAPI Intern" at QuantumLeaf Technologies; required Python/SQL/REST
APIs/Git, preferred FastAPI/Flask/PostgreSQL/Docker/Agile):

- Keyword alignment correctly classified Python/SQL/REST APIs/Git/FastAPI/PostgreSQL
  as supported, Flask/Docker as partial (Flask via `RELATED_TERMS["fastapi"]`,
  Docker via the learning-only section), and Agile as unsupported.
- Projects correctly ranked the backend project (AI Career Companion) above the
  unrelated portfolio project.
- Ten generated claims (summary, both education-referencing cover-letter sentences,
  the skills sentence, the project citation, the experience citation) were each
  manually checked against `source_path`/`sources` and found byte-traceable to the
  actual uploaded resume text — none fabricated.
- Editing only the summary and saving correctly left the cover letter's
  `user_edits.edited_fields` untouched after a bug fix (see below); refreshing the
  page (a fresh navigation, re-fetching from the backend) showed the edit persisted.
- Regenerating created a new version (v1 -> v2) while v1 remained readable unchanged.
- Exporting the resume as PDF returned a valid `%PDF`-prefixed file with the correct
  `Content-Disposition`/`Content-Type` headers.

**Bug found and fixed during this validation**: `saveEdits()` in `App.tsx` originally
sent both `summary` and `cover_letter_text` on every save regardless of whether the
user had actually touched both fields, so an untouched cover letter was incorrectly
flagged `user_edited`. Fixed to only include a field in the `PATCH` payload when its
draft value differs from the currently loaded value.

## LLM upgrade — live validation (2026-09-24)

**No real hosted LLM account (OpenAI, Anthropic, etc.) was available/configured in
this environment.** To validate the LLM layer's actual wiring rather than only its
in-process logic (already covered by `test_customization_llm.py`'s fake providers),
a local mock server implementing the real OpenAI chat-completions wire format
(`POST /chat/completions`, JSON-mode response) was stood up on `localhost`, and the
backend was pointed at it via `LLM_PROVIDER=openai_compatible`,
`LLM_BASE_URL=http://localhost:8098`, `LLM_MODEL=mock-model` — exercising the real
`OpenAICompatibleProvider` over a real HTTP call, not a bypassed fake. This proves the
provider integration itself (request shape, `httpx` call, JSON-mode parsing, timeout/
error handling) is correct; it does **not** demonstrate a genuine large language
model's actual rewriting quality/creativity, since the mock server's "rewriting" logic
is a simple deterministic transformation, not real language generation. **LLM
integration is ready, but no live third-party model was configured or tested in this
session.**

With that mock endpoint live, the full flow was run in a real browser: login (existing
user) -> job details (`JOB-0035`) -> Customize Application -> Regenerate. The response
correctly showed the **"AI Enhanced"** badge with *"Rewritten by openai_compatible
(mock-model), validated against your evidence."*, a genuinely different (not
byte-identical) summary and bullet wording than the deterministic baseline, a passed
grounding check, and populated "Supported by" provenance sections on every bullet,
the summary, and the cover letter. Editing one project bullet and saving persisted
correctly across a full page navigation/reload (verified via direct textarea
inspection before and after). Exporting the resume as PDF from this AI-enhanced,
user-edited version returned `200 OK`.

**Fallback path, live**: the mock server was then stopped (simulating a provider
outage) and Regenerate clicked again. The UI correctly created a new version tagged
**"Grounded Fallback"**, displayed exactly the required message — *"AI enhancement
unavailable or failed validation. A grounded fallback version is shown."* — and the
version switcher preserved the prior `v3 · AI Enhanced` entry alongside the new
`v4 · Grounded Fallback` one. The UI never hung or showed a blank/stuck state.

**Manual claim audit (LLM-enhanced version)**: every resume claim (summary, both
project bullets, the experience bullet) and every cover-letter paragraph was checked
against its `evidence_ids` -> `EvidenceRecord.source_path`/`raw_text`. All resolved to
real, unmodified text from the uploaded resume (the rewritten bullets were the
original text plus a non-factual "(tailored for ...)" suffix from the mock server, so
no claim was altered in a way that could be false). **One imprecision was found and
is recorded here rather than hidden**: one cover-letter sentence claimed "Python,
SQL, REST APIs" but cited evidence for "Python, FastAPI" — the underlying claim was
still fully true (SQL and REST APIs are both genuinely supported skills for this
candidate), but the specific `evidence_id` citation did not topically match the exact
wording. The current validator checks that cited evidence exists and that the text
contains no unsupported/fabricated claims — it does not yet enforce that each
individual named skill in a sentence has its own matching citation. Documented under
Known limitations below as a validator enhancement opportunity, not a grounding
failure (a real LLM, prompted to cite evidence per-claim as instructed, would be
expected to align these more precisely than this simplistic mock did).

## Known limitations

- **No genuine hosted LLM was tested in this session** (see above) — the provider
  abstraction and full request/validate/repair/fallback wiring are verified against a
  real HTTP mock, not against OpenAI/Anthropic/etc. Configuring `LLM_PROVIDER`,
  `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` against a real account is expected to
  work unchanged (the wire format is the same), but has not been observed directly.
- **Evidence-id citation is checked for existence, not per-claim topical precision** —
  the validator confirms every cited `evidence_id` was actually offered and that the
  text contains no unsupported keyword or fabricated pattern, but does not verify that
  a specific named skill within a sentence is backed by the specific evidence_id cited
  for that sentence (see the live-audit finding above). In practice this only matters
  when multiple cited skills are all independently true but loosely cross-referenced;
  it can never let an unsupported or fabricated claim through, since those are
  separately blocked by the keyword/metric/leadership/years checks.
- **Bullet-level user edits are not re-validated** — once a user edits a bullet,
  summary, or cover letter, it is marked `user_edited` and displayed as such, but its
  content is not run back through the fabrication validator (per the explicit
  requirement that a user's own edits are not treated as verified, AI-generated
  evidence — they are the user's own words, shown as such, not silently gated).

## Quality fixes (2026-09-24)

A manual review of real generated output surfaced several polish issues, all fixed
and regression-tested (`backend/tests/test_customization_quality.py`):

- **Category-label "skills"** — a resume whose Skills section uses bare category
  headers on their own line ("Programming" / "Backend" / "Databases" / "Web" /
  "Tools", each followed by a comma-separated list) had those headers preserved
  as if they were skills themselves. Root cause: M1's `structured_resume.
  _explicit_skill_items` *intentionally* keeps every unrecognized Skills-section
  item verbatim (documented, deliberate — see Milestone 3.1's manual-review-fixes
  section — so a legitimate-but-unrecognized skill like "Frontend Development" is
  never silently dropped). Rather than weakening that intentional M1 behavior,
  `customization_evidence.CATEGORY_LABEL_TERMS` / `is_category_label` filters this
  small, explicitly-named set of category-header words out of M3.2's own tailored/
  exported skill list and evidence pool only — `structured_resume.data` itself,
  and the "original order" skill display, are untouched and still show the
  parser's raw output for transparency.
- **Professional summary** — previously could copy the full raw education line
  (institution, graduation year, CGPA, coursework) into the summary.
  `customization_evidence.short_education_phrase` extracts only the degree/field
  clause; `_build_summary` now composes a concise 2-3 sentence, role-specific
  paragraph (education + top supported skills, optionally the top relevant
  project) rather than a raw data dump. Applied to both the deterministic
  fallback and the LLM system prompt (which now explicitly instructs the model
  not to copy raw education/project lines verbatim).
- **Cover letter** — restructured to opening / current background / strongest
  relevant evidence / role alignment / closing, targeting roughly 250-400 words.
  `customization_evidence.summarize_clause` extracts a single grounded clause
  from raw evidence (skipping a leading "{title} at {company}, {dates}"
  sentence in favor of the actual work description, and truncating a long
  clause) — a verbatim shortening, never a paraphrase — so evidence is
  summarized rather than dumped. A shared `join_terms` helper fixes
  inconsistent/incorrect comma placement in skill lists ("X and Y" for two
  items, an Oxford comma for three or more). No recipient name is ever
  invented ("Dear Hiring Team,"); the candidate's own real name signs the
  closing.
- **Bullet rewriting quality** — the LLM system prompt now includes a concrete
  before/after example of the expected rewrite quality (polished, professional,
  identical facts) and an explicit list of the specific fabrication patterns
  that must never be introduced (metrics, AWS, Docker, leadership, team size,
  years of experience) unless literally present in the offered evidence.

**Live re-verification**: regenerating against a real Gemini account reproduced
the "Grounded Fallback" the report was about — root-caused to `HTTP 429
RESOURCE_EXHAUSTED`, specifically Gemini's **free-tier daily quota**
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, 20 requests/day for
`gemini-3.6-flash`), exhausted by cumulative testing across sessions — not a
code or config defect. Since the quota is scoped per-model, `LLM_MODEL` was
switched to `gemini-flash-lite-latest` (a real, currently-available Gemini
model with separate, unused quota) to demonstrate a genuine live success: the
UI correctly showed **"AI Enhanced — Rewritten by openai_compatible
(gemini-flash-lite-latest), validated against your evidence."**, with a 33-word
2-sentence summary, a bullet rewrite matching the "Built..." -> "Developed..."
style requested, and a natural 231-word five-paragraph cover letter — all
grounding-clean (no Docker/AWS/metrics/team-size/years-of-experience found).
Save/refresh persistence and PDF export were also re-confirmed on this
AI-enhanced, user-edited version. `LLM_MODEL=gemini-3.6-flash`'s daily quota
resets on Google's normal schedule (or immediately on a paid plan) and can be
restored in `backend/.env` at any time — both are genuine, currently-supported
Gemini models.

**A second dev-environment root cause, now fixed at the process-management
level**: `uvicorn --reload`'s actual worker is spawned via `multiprocessing.
spawn_main`, whose OS command line contains no literal "uvicorn" — so a
process-matching filter like `CommandLine -like '*uvicorn*'` (used earlier in
this project's own dev-server cleanup steps) silently misses it, leaving an
orphaned worker holding the old in-memory config still bound to the port
after the reloader itself is killed. This explains the repeated "stale
process serving an old key/model" symptom encountered while iterating on this
project's LLM configuration. Restarting the backend cleanly now means killing
every `python.exe`/`node.exe` process tied to the target port, not just ones
whose command line happens to contain "uvicorn".
