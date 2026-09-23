# Milestone 3.2 — Resume & Cover Letter Customization Agent

Generates a role-specific tailored resume and cover letter from a student's existing
structured resume/profile and a selected internship. Like Milestones 2.3 and 3.1, no
LLM is used: every claim in the output is either (a) selected/reordered/lightly
formatted original resume text, or (b) a template-assembled sentence built strictly
from known structured fields, with an explicit source citation. Nothing is generated
freely and nothing is trusted without a traceable source.

## Why no LLM

The milestone's own grounding rule is non-negotiable: every generated claim must be
traceable to real student evidence, and an unsupported job keyword must never be
inserted into a claim. A deterministic pipeline makes this trivially provable — a
bullet's `tailored_text` is, by construction, the original text with only whitespace/
punctuation normalization, so it cannot contain an invented claim. An LLM-based
rewrite step could not offer that guarantee without extensive post-hoc validation,
and this project has no LLM/generative-API dependency anywhere else in the stack
(`app/services/job_matching.py`, `app/services/skill_gap_service.py`) — introducing
one here, for the one feature where hallucination is explicitly called out as the
central risk, would have been the wrong tradeoff.

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
Resume customization: relevance ranking, skill reordering, summary
composition                 (app/services/resume_customization_service.py)
        v
Cover letter composition    (app/services/cover_letter_service.py)
        v
Unsupported claim validator (app/services/customization_validator.py)
        v
Persisted, versioned ApplicationCustomization
        v
Frontend review/edit  ->  export (PDF/DOCX)
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
validation result, and user edits. `UniqueConstraint(resume_id, job_id, version)`.
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

The Customize Application page shows: a version switcher (regenerate creates a new
version, never overwrites); a grounding-check banner ("passed" or "review required"
with the validator's warnings); a keyword alignment section (supported / partially
supported / unsupported chips, with an explicit note that unsupported keywords are
never added); original-vs-reordered skills; projects ranked by relevance with their
matched job keywords; experience/internship bullets; an editable summary and cover
letter (each showing a "user edited" notice once touched); and PDF/DOCX export
buttons for both documents (fetched as a blob with the session cookie and downloaded
client-side, not a plain cross-origin link).

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

## Live E2E validation and manual grounding audit (2026-09-23)

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
