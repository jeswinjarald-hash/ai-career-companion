# Milestone 2.2 — RAG Pipeline & Semantic Search

The internship knowledge base uses the canonical JSON dataset from `backend/data/internships/`.

> **Note (Career Opportunity Generalization):** the canonical dataset was expanded from
> 180 internship-only records to 320 records spanning internships, entry-level jobs,
> graduate programs, trainee and apprenticeship roles (`career_opportunities_320.json`).
> The pipeline described below is unchanged — see
> [`docs/CAREER_OPPORTUNITY_GENERALIZATION.md`](CAREER_OPPORTUNITY_GENERALIZATION.md)
> for the dataset audit, composition, and migration details.

## Pipeline

Job dataset -> structured chunks -> local embeddings -> FAISS exact index -> query embedding -> chunk retrieval -> job-level aggregation -> top-k jobs

Each job creates three deterministic chunks: `overview`, `requirements`, and `responsibilities`. Chunk IDs use the stable parent ID, for example `JOB-0001::requirements`.

Embeddings use `sentence-transformers/all-MiniLM-L6-v2`, are normalized, and are stored in an exact `faiss.IndexFlatIP` index. Inner product therefore represents cosine similarity. Search groups matching chunks by `job_id`; its retrieval score is the best chunk score plus 5% of additional matched chunk scores. This is retrieval relevance only, not resume compatibility scoring.

## Build and use

From the repository root:

```powershell
cd backend
..\.venv\Scripts\python.exe scripts\build_job_vector_index.py
```

The build writes generated files to `backend/data/vector_store/`:

- `internship_jobs.faiss`
- `internship_jobs_metadata.json`

The files are deliberately ignored because they are reproducible build artifacts and the model cache is external to the repository.

The service API is:

```python
from app.services.job_search_service import search_jobs

results = search_jobs("Python machine learning internship using pandas and SQL", top_k=5)
```

The HTTP endpoint is `GET /api/jobs/search?q=python+machine+learning&top_k=5`. The vector store must be built explicitly before search; normal search never silently rebuilds it.

M2.2 does not score resume compatibility, compare a candidate to jobs, or generate recommendation explanations. Those behaviors belong to M2.3.
