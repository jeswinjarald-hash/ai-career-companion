from collections import defaultdict

from app.schemas.job_chunk import JobChunk
from app.schemas.job_posting import JobPosting
from app.schemas.job_chunk import JobSearchResult
from app.services.embedding_service import embed_query
from app.services.job_vector_store import load_vector_store


class JobSearchError(ValueError):
    pass


def search_jobs(query: str, top_k: int = 5) -> list[JobSearchResult]:
    if not query.strip():
        raise JobSearchError("Search query must not be empty.")
    if not 1 <= top_k <= 20:
        raise JobSearchError("top_k must be between 1 and 20.")

    index, chunks = load_vector_store()
    scores, positions = index.search(embed_query(query).reshape(1, -1), index.ntotal)
    grouped: dict[str, list[tuple[float, JobChunk]]] = defaultdict(list)
    for score, position in zip(scores[0], positions[0]):
        if position >= 0:
            grouped[chunks[int(position)].job_id].append((float(score), chunks[int(position)]))

    jobs_by_id = {job.job_id: job for job in _load_jobs()}
    results: list[JobSearchResult] = []
    for job_id, matches in grouped.items():
        job = jobs_by_id[job_id]
        matches.sort(key=lambda match: match[0], reverse=True)
        best_score = matches[0][0]
        additional_score = sum(score for score, _ in matches[1:]) * 0.05
        results.append(
            JobSearchResult(
                job_id=job.job_id,
                job_title=job.job_title,
                company=job.company,
                domain=job.domain,
                location=job.location,
                work_mode=job.work_mode,
                employment_type=job.employment_type,
                required_skills=job.required_skills,
                preferred_skills=job.preferred_skills,
                similarity_score=best_score + additional_score,
                matched_chunk_types=sorted({chunk.chunk_type for _, chunk in matches}),
                matched_text_preview=matches[0][1].text[:240],
            )
        )
    results.sort(key=lambda result: result.similarity_score, reverse=True)
    return results[:top_k]


def _load_jobs() -> list[JobPosting]:
    from app.services.job_dataset_service import load_job_postings

    return load_job_postings()
