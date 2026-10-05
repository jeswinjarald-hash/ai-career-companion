# AI Career Companion

An Infosys internship project: a web application that turns a student's resume into
grounded career actions — semantic opportunity search, explainable job matching,
skill-gap analysis, tailored resume and cover letter, interview preparation, a
conversational assistant, and an application tracker.

The system is a **deterministic + optional-LLM hybrid**. Every feature works without
an LLM (`LLM_PROVIDER=none`, the default). If an OpenAI-compatible model is configured, it
only rewrites already-grounded content; its JSON output is validated against the
candidate's evidence and falls back to the deterministic result on any failure.

This is a local development and evaluation implementation. It is not deployed.

**Full documentation:** [`docs/FINAL_TECHNICAL_DOCUMENTATION.md`](docs/FINAL_TECHNICAL_DOCUMENTATION.md)

## Status

Milestones M1, M2, M3, M4.1 (tracker), M4.2 (evaluation), M4.3 (optimization) and
M4.4 (final documentation and release audit) are complete. Not implemented: learning-
roadmap generation and roadmap progress (the pages say so). Known limitations are listed in
§26 of the final documentation.

## Architecture at a glance

```
React + Vite + TypeScript  →  FastAPI  →  auth (HttpOnly session cookie) + per-user ownership
  → resume pipeline (PDF/DOCX → text → sections → structured resume → candidate context)
  → retrieval (all-MiniLM-L6-v2, 384-d → FAISS IndexFlatIP, 960 chunks, index v1.2)
  → deterministic matching / skill gap / grounded customization / interview prep / assistant
  → application tracker → SQLAlchemy + SQLite
```

Knowledge base: `backend/data/internships/career_opportunities_320.json` — 320 curated
opportunities (internships, entry-level, graduate, trainee, apprenticeship) across 15
technology domains.

## Final evaluation (offline, deterministic pipeline)

From `backend/data/evaluation/m4/results/` (M4.2 frozen baseline → M4.3 final):

| Measure | Baseline | Final |
|---|---:|---:|
| Retrieval Hit@1 / MRR@10 (26 labelled queries) | 0.885 / 0.942 | 1.000 / 1.000 |
| Off-topic queries flagged / genuine queries flagged | 0/12 / 0/26 | 11/12 / 0/26 |
| Grounding violations / fault injections detected | 0 / 9 of 9 | 0 / 10 of 10 |
| Conversation turns with desired behaviour | 12/16 | 15/16 |
| Backend tests | 374 passed, 6 xfailed | 464 passed, 1 xfailed |

The evaluation set is small and synthetic; live LLM output was not evaluated.

## Quick start (Windows PowerShell, from the repository root)

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe scripts\build_job_vector_index.py   # index is not committed
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs
```

In a second terminal at the repository root:

```powershell
npm install
npm run dev                                                      # http://localhost:5173
```

Optional settings: copy `backend/.env.example` to `backend/.env` and `.env.example` to
`.env`. Never commit real keys. The first index build downloads the embedding model
once.

## Verification

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe scripts\validate_job_dataset.py
..\.venv\Scripts\python.exe scripts\run_m4_evaluation.py --output-dir $env:TEMP\m4_eval
cd ..
npx tsc -b
npm run lint
npm run build
```

## Documentation

| Document | Content |
|---|---|
| [`docs/FINAL_TECHNICAL_DOCUMENTATION.md`](docs/FINAL_TECHNICAL_DOCUMENTATION.md) | Architecture, all milestones, evaluation, optimization, security, performance, demo workflow, limitations, setup, API |
| [`docs/MILESTONE_1.md`](docs/MILESTONE_1.md) | Profile and resume pipeline (authentication was added later, in the M1/M2 integration) |
| [`docs/MILESTONE_2_2.md`](docs/MILESTONE_2_2.md), [`docs/MILESTONE_2_3.md`](docs/MILESTONE_2_3.md) | Semantic retrieval, matching |
| [`docs/MILESTONE_3_1.md`](docs/MILESTONE_3_1.md) – [`docs/MILESTONE_3_4.md`](docs/MILESTONE_3_4.md) | Skill gap, customization, interview prep, assistant |
| [`docs/CAREER_OPPORTUNITY_GENERALIZATION.md`](docs/CAREER_OPPORTUNITY_GENERALIZATION.md) | 320-record dataset generalization |
| [`docs/MILESTONE_4.md`](docs/MILESTONE_4.md) | Application tracker; index of M4.2–M4.4 artifacts |
| [`backend/data/evaluation/m4/README.md`](backend/data/evaluation/m4/README.md) | Evaluation framework, label policy, how to run |
| [`docs/file-purpose-guide.md`](docs/file-purpose-guide.md) | What each file is for |

Resumes, databases and `.env` files contain personal or secret data and stay local; see
`.gitignore`.
