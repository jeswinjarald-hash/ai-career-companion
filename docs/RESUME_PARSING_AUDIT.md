# Resume Parsing and Grounding Audit

Date: 2026-10-10 · branch `develop` · parser version **4** (`PARSER_VERSION` in
`backend/app/services/structured_resume.py`).

This document records defects found while auditing the resume pipeline against real
uploaded resumes (not only well-formed test strings), what was changed, and how it was
verified. All fixtures in the repository are synthetic; personal data that was present in
one older test fixture has been replaced.

## 1. Root causes found

| # | Symptom seen in the app | Root cause | Layer |
|---|---|---|---|
| 1 | Projects named "Society", "Finance", "Management", "Built using Developed a full-stack…" | Google Docs (Skia) PDFs draw every word in its own text object on a flipped coordinate system; pypdf's default `extract_text()` emits a line break between every word. The broken text was persisted and every capitalised word became a project. | PDF extraction |
| 2 | Fragments like "Built", "using Node, Express", "HTML," as projects | A blank line (DOCX empty paragraphs, PDF page breaks) was treated as an unconditional project boundary, and the first line of every block became a title without validation. | Structuring |
| 3 | Dates, "(OOP)", "NPTEL CERTIFIED IN JAVA", "ENGLISH" detected as section headings; certifications and languages lost | Any all-caps line of ≤ 6 words was accepted as a custom heading. | Section detection |
| 4 | Sidebar skills/languages and header contact details missing from DOCX resumes | Only body paragraphs and tables were read; Word text boxes (`w:txbxContent`) and page headers were ignored. | DOCX extraction |
| 5 | "ﬁnancial", "Node​.js", NBSP-joined words | Ligatures, zero-width characters, soft hyphens and non-breaking spaces were not normalised. | Normalisation |
| 6 | Fragment records cited in recommendation reasoning, customization cards and interview questions | Every downstream service consumed `structured_resume.projects` without a reliability check. | Downstream evidence |
| 7 | "Grounding check passed" while the resume structure was unreliable; invented technologies/degrees/employers not caught | `ValidationResult.passed` ignored parser warnings; the validator only checked job keywords and metric/leadership/years patterns; user edits were never re-validated. | Grounding |
| 8 | Skill Gap "We couldn't connect to the skill gap service" with nothing logged | Starlette's `exception_handler(Exception)` runs outside `CORSMiddleware`, so an unhandled 500 had no CORS headers; the browser blocked it and the UI could only report a network failure. Reproduced exactly with the backend stopped (`ERR_CONNECTION_REFUSED`). | API error path |
| 9 | HTTP 500 under concurrent generation requests | Customization / interview versions were computed as `max(version)+1`; two concurrent requests for the same resume/opportunity violated the UNIQUE constraint (4 of 60 in a concurrency probe). | Persistence |
| 10 | Assistant: "I cannot determine which project is most relevant" | The profile-summary facts contained project titles only, not their technologies. | Assistant grounding |
| 11 | Refreshing Skill Gap / Customize / Interview Prep lost the selected opportunity | The selection lived only in React state; those URLs carried no job id. | Frontend routing |

## 2. Changes

**Extraction and normalisation**
- `pdf_extraction.py`: when plain-mode text is word-fragmented (`is_word_fragmented`),
  the page is rebuilt from each text run's device-space position via pypdf's visitor,
  keeping content-stream (column) order. Normal PDFs are unaffected.
- `docx_extraction.py`: page-header paragraphs and floating text boxes are extracted (VML
  fallback copies skipped to avoid duplicates).
- `text_utils.py`: ligatures expanded; invisible characters removed; typographic spaces
  normalised; lone bullet glyph lines (including pypdf's DEL decoding) reattached.

**Section detection and structuring**
- Custom (unrecognised all-caps) headings must contain no digits, not end on a connector,
  not continue an all-caps line, not directly follow an empty heading, and be followed by
  content. The first line (the candidate's name) is never a custom heading.
- Wrapped lines ending in a connector ("Built using", "Node,Express and") or comma are
  rejoined; blank-line blocks only start a project when their first line reads as a title;
  "Name — Built using React" annotations are recognised.
- `is_plausible_project_title` / `is_reliable_project` are the single shared reliability
  rule. Unreliable records are kept in the stored data (source evidence is never deleted)
  but skipped by matching, skill gap, customization evidence, cover letter, interview
  prep and the assistant.
- Parser warnings include `fragmented_project_titles` and `word_fragmented_text`.

**Versioning and reprocessing**
- Every structured result records `parser_version`. Results from an older version are
  served with an `outdated_parser_version` warning (read-only; nothing is rewritten).
- The Results page offers **Reprocess with current parser**, which re-runs extraction →
  sections → structure → context on the *stored original file*; the upload is kept and no
  duplicate resume record is created. Existing customizations / interview preparations /
  skill-gap analyses are then marked stale by the existing timestamp comparison.
- `GET /api/resumes/{id}/structured` and `POST /api/resumes/{id}/structure` add a
  serve-time `evidence_eligible` flag to each project (computed, not persisted).

**Grounding**
- `check_unsupported_claims` (in `customization_validator.py`) rejects technologies,
  quoted project/title names, degrees, employers, work-experience claims and
  awards that are absent from the candidate's evidence; job-posting text may be quoted.
- Validation is never reported as passed while parser warnings exist; customization
  and interview generation refuse with HTTP 409 when only fragments remain.
- User edits to generated materials are re-validated on save.

**API / persistence**
- Unhandled exceptions now become logged JSON 500s *inside* the CORS layer.
- Customization / interview version allocation retries on a concurrent conflict.

**Frontend**
- Results page: extraction summary, structured project entries (title, technologies,
  description, "Not used as evidence" badge), parsed degree / graduation badges,
  Languages card, reprocess action on outdated results.
- Long generation shows a real elapsed-time status panel (no simulated progress).
- Recommendation reasoning cites project titles instead of full descriptions.
- Job-scoped pages keep the opportunity in the URL (`?job=`) so refresh restores them.

## 3. Verification

- Backend suite: **547 passed, 1 xfailed** (the xfail is the pre-existing CV06 case).
  New regression files: `tests/test_resume4_regressions.py`,
  `tests/test_video_audit_regressions.py`, with sanitized fixtures
  `tests/skia_pdf_fixture.py` (reproduces the Google Docs layout and pypdf failure) and
  `tests/docx_layout_fixture.py` (header + text-box sidebar).
- `npm run lint` clean, `npx tsc -b` passes, `npm run build` succeeds.
- Browser (isolated scratch backend + database, LLM disabled): sign-up, upload through
  the real file input of a synthetic Google-Docs-style PDF, Results, Recommendations,
  Skill Gap, Customization, Interview Prep, refresh persistence, unsupported file,
  malformed PDF (400), minimal resume (empty states), insufficient evidence (409),
  older-parser result + reprocess, backend stop → error → restart → retry, 375 px layout.
- Live LLM (`openai_compatible`, synthetic resume only): customization produced
  `mode=llm` with grounding passed; interview prep's LLM output mentioned an unsupported
  keyword and correctly fell back to the deterministic version; the assistant answered
  from project technologies after fix #10.

## 4. Remaining limitations

- No OCR: image-only PDFs still fail explicitly.
- The position-based PDF rebuild is heuristic; it is verified on the observed Google
  Docs layout and synthetic fixtures, not on every template (tables, rotated text and
  multi-column layouts drawn in interleaved order are untested).
- Experience is still one entry per section, not split per role.
- Reprocessing is manual (by design, to avoid silently rewriting user data).
- The browser's native file-picker dialog was not driven; files were attached to the
  real `<input type="file">` programmatically, which runs the same app code.
- Live LLM behaviour was spot-checked on one synthetic resume; it is not an evaluation.
- Older Git history still contains the personal data that was removed from the test
  fixture; history was not rewritten.
