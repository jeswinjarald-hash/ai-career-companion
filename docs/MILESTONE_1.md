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
