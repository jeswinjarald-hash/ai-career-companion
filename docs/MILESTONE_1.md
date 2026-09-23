# Milestone 1 - Candidate Understanding Foundation

## Objective

Milestone 1 turns a persisted Career Profile and a validated PDF/DOCX resume into deterministic structured resume data and persisted Candidate Context. It is local, rule-based processing; it is not an AI analysis service.

## Architecture

```text
React
  -> FastAPI
  -> Profile / Resume APIs
  -> validation and local storage
  -> PDF/DOCX text extraction
  -> section detection
  -> deterministic structured extraction
  -> Candidate Context
  -> SQLite persistence
```

## Implemented Features

- Candidate profile create, retrieve, update, and persistence.
- PDF and DOCX multipart upload with content validation and 10 MiB limit.
- Local UUID-based resume storage.
- PDF extraction with `pypdf` and DOCX extraction with `python-docx`.
- Shared text normalization, page/paragraph/table text persistence.
- Deterministic section detection with aliases, header preservation, custom sections, and ordered repeated sections.
- Deterministic vocabulary-based skills, conservative education, experience/internship, project, certification, achievement, and interest extraction.
- Persisted structured resume JSON and profile/resume Candidate Context JSON.
- Existing Resume Analyzer now uses the real upload and processing pipeline.

## APIs

- `POST /api/profiles`, `GET /api/profiles/{profile_id}`, `PATCH /api/profiles/{profile_id}`
- `POST /api/profiles/{profile_id}/resumes`
- `GET /api/resumes/{resume_id}`
- `GET /api/profiles/{profile_id}/resumes`
- `POST /api/resumes/{resume_id}/extract-text`
- `GET /api/resumes/{resume_id}/extraction`
- `POST /api/resumes/{resume_id}/detect-sections`
- `GET /api/resumes/{resume_id}/sections`
- `POST /api/resumes/{resume_id}/structure`
- `GET /api/resumes/{resume_id}/structured`
- `POST /api/profiles/{profile_id}/candidate-context?resume_id={resume_id}`
- `GET /api/profiles/{profile_id}/candidate-context?resume_id={resume_id}`

## Data Models

`CandidateProfile`, `Resume`, `ResumeExtraction`, `ResumeSection`, `StructuredResume`, and `CandidateContext` are persisted with SQLAlchemy and SQLite. Binary resume files remain in configured local storage; extracted and structured data is stored in the database.

## Resume Processing Flow

`uploaded -> extracting_text -> text_extracted -> structured`. Section rows are generated between extraction and structuring. Extraction failures use `extraction_failed`. Structured and context generation are idempotent updates.

## Extraction Rules

Skills use a centralized conservative vocabulary and aliases. Education, experience, internships, and projects preserve `raw_text` and only fill fields when a simple deterministic pattern is reliable. No LLM or external model is called.

## Limitations

- Scanned/image-only PDFs are unsupported because OCR is not included.
- Rule-based extraction may not understand every resume layout.
- DOCX table ordering follows the accessible document body order.
- Authentication and real multi-user mapping remain deferred.
- Career recommendations, skill-gap analysis, roadmap generation, RAG, and agents remain mock/demo modules.

## Testing

Python 3.12 `.venv` was used. The backend suite passes with `27 passed`. Frontend `npm run build` and `npm run lint` pass. Synthetic PDF and DOCX flows were exercised through the live HTTP API, including section detection, structured output, candidate context, and restart retrieval.

## Future Milestones

Candidate Context is the input boundary for later career recommendations, skill-gap analysis, roadmap generation, RAG, and multi-agent architecture. Those features are not implemented as part of Milestone 1.

## Resume Parser Robustness Audit (2026-09-23)

A manual review found real resumes (no bullet markers, an inline "Project Name —
Built using X, Y, Z" title/tech-annotation line, wrapped paragraph descriptions, and
uncommon section headings) produced badly fragmented output — dozens of one-word
"projects" and unrelated prose words reported as "skills". Root-caused and fixed in
`app/services/structured_resume.py` and `app/services/section_detection.py`:

- **Ordering bug**: a new project's title line (with several technologies named
  after it) was checked against the generic "is this a bare tech-stack list" rule
  *before* the "is this actually a new project" rule, so it was absorbed as more
  technologies for the *previous*, about-to-close project instead of starting a new
  one. Title/annotation detection now runs first.
- **No positive title validation**: any unindented, non-tech-line sentence became a
  new "project". `_looks_like_project_title` now requires structural signals
  (a short line, no lowercase/verb lead, no terminal punctuation) — and, as a second
  line of defense, `_merge_content_less_fragments` folds a title-only "project" (one
  that picked up neither a description nor a technology) back into its neighbor
  after the fact, so an occasional false positive can't survive as its own entry.
- **Vocabulary-dependent annotation detection**: recognizing "Flutter, Firebase" as
  a tech annotation used to require both names to be in the curated skill
  vocabulary — which can never be exhaustive. Annotation detection now checks the
  tail's *list shape* (2+ short comma/pipe/slash-separated segments) instead, and an
  unrecognized term is kept verbatim rather than dropped, the same policy already
  used for a dedicated Skills section's self-declared items.
- **Skills-section contamination**: an unrecognized section heading's content could
  silently fall into the preceding Skills section and, together with the "preserve
  every self-declared item" policy, surface as dozens of prose-word "skills". A
  sanity cap (`_MAX_TRUSTED_EXPLICIT_SKILL_ITEMS`) now falls back to conservative,
  vocabulary-only matching whenever an "explicit" skills list looks implausibly
  long. The section-heading alias list was also substantially broadened (more
  Education/Experience/Projects/Skills/Certifications/Languages wordings).
- **DOCX blank-paragraph loss**: `docx_extraction.py` silently dropped every blank
  paragraph, destroying the blank-line project/education boundary signal for any
  DOCX upload (PDF extraction preserves that signal already, or rather — see below —
  frequently does not, which is exactly why the defenses above don't depend on it).
- Verified empirically that `pypdf`'s default text extraction does **not** reliably
  preserve blank-line paragraph gaps as blank text lines, so the parser cannot
  depend on that signal for PDF uploads — the structural/merge-based defenses above
  are what make PDF resumes robust, not blank-line detection alone.
- Non-destructive sanity warnings (`suspicious_project_count`,
  `many_single_word_project_titles`, `excessive_unrecognized_skills`,
  `truncated_education_entry`, ...) are computed after structuring and persisted in
  the structured data as `parser_warnings`; the Resume Results page shows a
  "Processed with warnings" notice when present, without blocking the resume.

Fixture corpus and PDF/DOCX parity tests: `backend/tests/test_resume_parser_robustness.py`.
Targeted regressions for the specific failure mode: `backend/tests/test_resume_parser_real_world.py`.

**Known limitation, stated plainly**: this remains heuristic, structure-aware
parsing with validation, not universal resume understanding. An unusual layout can
still produce an imperfect (though no longer explosively wrong) result; the
sanity-warning mechanism exists specifically to surface that rather than hide it.
