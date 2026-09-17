# AI Career Companion

AI Career Companion is an agentic career-support platform for students. The architecture combines a candidate profile with resume parsing and structured extraction before future AI services use that context.

## Current Development Status

Status: Milestone 1 candidate-understanding foundation

The React + Vite + TypeScript frontend currently represents the documented candidate-understanding flow:

- manual candidate profile details
- PDF and DOCX resume selection validation
- resume processing states
- structured extraction preview for skills, projects, and education
- responsive workspace navigation

The Career Profile and Resume Analyzer pages use the FastAPI profile/resume services, and Career Recommendations uses the active structured resume for semantic retrieval and job-resume matching. Later architecture modules such as skill gaps, roadmaps, cover letters, interviews, and application tracking remain mock-backed and are not integrated.

## Run the frontend

```bash
npm install
npm run dev
```

Copy `.env.example` to `.env` when local frontend overrides are needed. `VITE_API_BASE_URL` selects the FastAPI origin and `VITE_PROFILE_ID` is the temporary development profile ID. After a profile is created, its returned ID is kept in browser localStorage until authentication provides a real user-to-profile mapping.

## Run the backend

The backend uses Python 3.12, FastAPI, SQLAlchemy, and SQLite for local persistence. Milestone 1 supports validated PDF/DOCX upload, text extraction, section detection, deterministic structured resume extraction, and persisted Candidate Context. No external LLM or OCR is used.

From the repository root, create and activate a virtual environment, then install the backend dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r backend/requirements.txt
```

Copy `backend/.env.example` to `backend/.env` when local environment overrides are needed. The development frontend origin is configured as `http://localhost:5173` by default.

Database configuration is controlled by `DATABASE_URL`. The default local value is `sqlite:///./data/ai_career_companion.db`, resolved from the `backend` directory. The database directory is created automatically, and the minimal candidate profile table is initialized when FastAPI starts. SQLite files remain local and are ignored by Git. A different SQLAlchemy-supported relational database can be selected by setting `DATABASE_URL` without changing the service layer.

Start the API from the `backend` directory:

```bash
cd backend
uvicorn app.main:app --reload
```

The health endpoint is available at `http://127.0.0.1:8000/health` and returns `{"status":"ok"}`.

The Career Profile API is available under `/api/profiles`. Use `POST /api/profiles` to create a profile, `GET /api/profiles/{profile_id}` to retrieve one, and `PATCH /api/profiles/{profile_id}` to update it. Requests and responses are documented in Swagger at `http://127.0.0.1:8000/docs`. The current development API uses the profile email as a duplicate-creation guard; authentication and multi-user profile mapping remain deferred.

### Resume Upload, Validation, and PDF Text Extraction API

Step 7 accepts only content-validated PDF and DOCX uploads without parsing them. Upload a file with `POST /api/profiles/{profile_id}/resumes` as multipart form field `file`; the response contains persisted metadata with status `uploaded`. Resume metadata can be retrieved with `GET /api/resumes/{resume_id}` or listed with `GET /api/profiles/{profile_id}/resumes`.

Uploaded files are stored locally under `RESUME_STORAGE_DIR` (default `./data/resumes`, resolved from the backend directory) using generated filenames. The original filename is retained as metadata, while internal storage paths are never returned. PDF signatures and readable structure are checked with `pypdf`; DOCX ZIP structure and required XML entries are checked with the Python standard library. A 10 MiB upload limit applies, and invalid or corrupt uploads are rejected before storage or database persistence.

For a validated PDF or DOCX, `POST /api/resumes/{resume_id}/extract-text` extracts text and persists a one-to-one `ResumeExtraction` record. PDFs use `pypdf`; DOCX files use `python-docx`. DOCX paragraphs and table rows are retained in document order where available, with table cells separated by `|`. Retrieve results with `GET /api/resumes/{resume_id}/extraction`. Reprocessing updates the existing extraction record. Image-only/scanned PDFs and empty DOCX files fail explicitly because OCR is not included. Structured resume analysis is not implemented. Resume files and extracted text contain personal information and remain local; do not commit them.

For extracted text, `POST /api/resumes/{resume_id}/detect-sections` performs deterministic, alias-based section boundary detection and `GET /api/resumes/{resume_id}/sections` retrieves the ordered result. Supported canonical sections include `summary`, `objective`, `skills`, `education`, `experience`, `internships`, `projects`, `certifications`, `achievements`, `activities`, `interests`, and `publications`. Text before the first heading is retained as `header`; unrecognized short uppercase headings are retained as `custom`. Repeated sections remain separate ordered rows, and rerunning detection replaces the previous rows. This stage does not extract structured skills, education, experience, projects, or other entities, and uses no LLM.

The complete Milestone 1 scope, APIs, models, limitations, and verification are documented in `docs/MILESTONE_1.md`.
