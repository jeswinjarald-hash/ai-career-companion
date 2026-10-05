# AI Career Companion File Purpose Guide

What each maintained file or folder is for. Generated and local-only files are listed at
the end. For the system design see
[`FINAL_TECHNICAL_DOCUMENTATION.md`](FINAL_TECHNICAL_DOCUMENTATION.md).

## Project Root

| File | Purpose |
| --- | --- |
| `README.md` | Project overview, quick start, verification commands, documentation index. |
| `package.json` / `package-lock.json` | Frontend npm scripts and dependencies (lock file: do not edit manually). |
| `index.html` | Vite entry document; loads `src/main.tsx`. |
| `vite.config.ts` | Vite configuration with the React plugin. |
| `eslint.config.js` | ESLint rules (TypeScript, React Hooks, React Refresh). |
| `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json` | TypeScript project references and strict settings. |
| `.env.example` | Frontend placeholder: `VITE_API_BASE_URL` (default `http://localhost:8000`). |
| `.gitignore` | Excludes secrets, local data, generated index, dependencies, builds, caches. |
| `public/` | Static files served by Vite. |

## Frontend (`src/`)

| File | Purpose |
| --- | --- |
| `main.tsx` | React bootstrap (`StrictMode`). |
| `App.tsx` | Application shell, authentication screens, path-based view routing and the page components (dashboard, profile, resume analyzer/results, careers, job details, skill gap, customize, interview prep, roadmap notice, assistant, progress, settings). All data comes from the backend API. |
| `App.css`, `index.css`, `profile.css` | Visual system, global base styles, profile page styles. |
| `config/api.ts` | Resolves the API base URL from `VITE_API_BASE_URL`. |
| `services/authService.ts` | Register, login, logout, current user. |
| `services/profileService.ts` | Career profile read/update. |
| `services/resumeService.ts` | Resume upload and processing pipeline calls. |
| `services/jobService.ts` | Opportunity search, job details, job matches. |
| `services/skillGapService.ts` | Skill gap analysis. |
| `services/customizationService.ts` | Resume / cover-letter customization, edits, regenerate, export. |
| `services/interviewPrepService.ts` | Interview preparation and mock-answer feedback. |
| `services/assistantService.ts` | Assistant conversations and messages. |
| `services/applicationService.ts` | Application tracker client (M4.1). |
| `components/common.tsx` | Small shared UI helpers. |
| `components/applications/*` | Tracker list, detail view, dashboard widgets, formatting helpers and styles (M4.1). |
| `assets/react.svg` | Vite starter asset, not used by the UI. |
| `vite-env.d.ts` | Vite type declarations. |

## Backend (`backend/`)

### Configuration and entry

| File | Purpose |
| --- | --- |
| `requirements.txt` | Python dependencies. |
| `.env.example` | Backend settings with placeholders (database, storage, embedding model, optional LLM). The real `backend/.env` is gitignored. |
| `app/main.py` | FastAPI app, lifespan (`init_db`, LLM-config status log), CORS, router registration. |
| `app/core/config.py` | `Settings` (pydantic-settings) and backend-root path resolution. |
| `app/core/database.py` | Engine, session dependency, `create_all` initialisation, legacy SQLite column helper. |

### API routers (`app/api/`)

`health.py`, `auth.py`, `profile.py`, `resume.py` (upload, pipeline steps, job matches),
`context.py` (candidate context), `jobs.py` (public catalogue search/details),
`skill_gap.py`, `customization.py`, `interview_prep.py`, `assistant.py`,
`applications.py` (M4.1). Endpoint list: final documentation §29.

### Models and schemas

`app/models/` holds the SQLAlchemy tables (users, auth sessions, profiles, resumes and
their extraction/sections/structured data, candidate contexts, career state including
customizations and interview preparations, conversations, progress events,
applications). `app/schemas/` holds the matching Pydantic request/response models.

### Services (`app/services/`)

| Area | Files |
| --- | --- |
| Auth / profile | `auth.py`, `profile.py` |
| Resume pipeline | `resume.py`, `resume_validation.py`, `pdf_extraction.py`, `docx_extraction.py`, `section_detection.py`, `structured_resume.py`, `candidate_context.py`, `text_utils.py` |
| Knowledge base and retrieval | `job_dataset_service.py`, `job_chunking.py`, `embedding_service.py`, `job_vector_store.py`, `job_search_service.py`, `retrieval_confidence.py` (M4.3) |
| Matching and skill gap | `job_matching.py`, `skill_relationships.py` (M4.3), `education_assessment.py` (M4.3), `skill_gap_service.py`, `skill_gap_evidence.py` |
| Customization | `resume_customization_service.py`, `customization_evidence.py`, `customization_keywords.py`, `customization_validator.py`, `customization_llm.py`, `cover_letter_service.py`, `customization_export_service.py` |
| Interview preparation | `interview_prep_service.py`, `interview_question_service.py`, `interview_evidence.py`, `interview_llm.py`, `interview_mock_service.py` |
| Assistant | `assistant_service.py`, `assistant_intent.py`, `assistant_context.py`, `assistant_handlers.py`, `assistant_llm.py` |
| Optional LLM | `llm_provider.py` (null provider and OpenAI-compatible `httpx` client) |
| Application tracker | `application_service.py` (M4.1) |
| Evaluation | `m2_4_evaluation.py` (historical M2.4), `m4_evaluation.py` (M4.2/M4.3 framework) |

### Scripts (`backend/scripts/`)

| File | Purpose |
| --- | --- |
| `validate_job_dataset.py` | Validates the canonical dataset and prints a summary. |
| `build_job_vector_index.py` | Builds the FAISS index and metadata into `data/vector_store/`. |
| `run_m2_4_evaluation.py` | Historical M2.4 evaluation runner. |
| `run_m4_evaluation.py` | Offline M4 evaluation; compares against the frozen M4.2 baseline. |

### Data (`backend/data/`)

| Path | Purpose |
| --- | --- |
| `internships/career_opportunities_320.json` | **Canonical** opportunity dataset (320 records). |
| `internships/career_opportunities_320.csv`, `job_posting_schema.json`, `validation_report.json`, `README.md` | CSV mirror, JSON Schema, validation summary, dataset documentation. |
| `evaluation/*.json`, `evaluation/results/` | Historical M2.4 evaluation inputs and results (unchanged). |
| `evaluation/m4/cases/` | M4 evaluation cases (retrieval positive/negative, synthetic candidates, conversations). |
| `evaluation/m4/results/` | Frozen M4.2 baseline, M4.3 experiment log, M4.3 report and final results. |
| `create_browser_fixture.py` | Generates a small synthetic DOCX used for browser testing (the output file is gitignored). |

### Tests (`backend/tests/`)

Pytest suite for every service and router. `conftest.py` blocks live LLM calls suite-wide.
M4-specific: `test_application_service.py`, `test_applications_api.py`,
`test_m4_2_evaluation_framework.py`, `test_m4_2_baseline.py`,
`test_m4_2_e2e_workflow.py`, `test_m4_3_optimizations.py`.

## Documentation (`docs/`)

| File | Purpose |
| --- | --- |
| `FINAL_TECHNICAL_DOCUMENTATION.md` | Canonical final documentation (architecture, milestones, evaluation, limitations, demo, setup, API). |
| `MILESTONE_1.md` | M1 candidate-understanding foundation. |
| `MILESTONE_2_2.md`, `MILESTONE_2_3.md` | Semantic retrieval; job–resume matching. |
| `MILESTONE_3_1.md` … `MILESTONE_3_4.md` | Skill gap, customization, interview preparation, assistant. |
| `CAREER_OPPORTUNITY_GENERALIZATION.md` | 180 → 320 record generalization. |
| `MILESTONE_4.md` | M4.1 application tracker; index to M4.2–M4.4 artifacts. |
| `file-purpose-guide.md` | This file. |

## Generated or Local-only (not committed)

| Path | Why |
| --- | --- |
| `backend/.env`, `.env` | Local settings, may contain an API key. |
| `backend/data/*.db` | Local SQLite database with user data. |
| `backend/data/resumes/` | Uploaded resumes (personal data). |
| `backend/data/vector_store/` | Generated FAISS index; rebuild with `build_job_vector_index.py`. |
| `backend/data/browser_text_resume.docx` | Generated test fixture. |
| `node_modules/`, `dist/` | npm packages and production build output. |
| `.venv/`, `.venv-*/`, `__pycache__/`, `.pytest_cache/` | Python environment and caches. |
| `.claude/` | Local tool launch configuration. |
