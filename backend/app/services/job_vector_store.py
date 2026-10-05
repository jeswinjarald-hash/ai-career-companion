import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.schemas.job_chunk import JobChunk
from app.services.embedding_service import embedding_dimension

VECTOR_STORE_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "vector_store"
INDEX_PATH = VECTOR_STORE_DIRECTORY / "internship_jobs.faiss"
METADATA_PATH = VECTOR_STORE_DIRECTORY / "internship_jobs_metadata.json"
# 1.2: the overview chunk leads with "<title> (<employment type>). " (M4.3 Experiment 8, V3).
INDEX_VERSION = "1.2"


class VectorStoreError(ValueError):
    pass


def build_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise VectorStoreError("Embeddings must be a non-empty two-dimensional array.")
    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype(np.float32)
    expected_dimension = embedding_dimension()
    if embeddings.shape[1] != expected_dimension:
        raise VectorStoreError(
            f"Embedding dimension {embeddings.shape[1]} does not match model dimension {expected_dimension}."
        )
    index = faiss.IndexFlatIP(expected_dimension)
    index.add(embeddings)
    return index


def save_vector_store(index: faiss.IndexFlatIP, chunks: list[JobChunk]) -> None:
    if index.ntotal != len(chunks):
        raise VectorStoreError("FAISS vector count does not match chunk metadata count.")
    VECTOR_STORE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_PATH))
    metadata: dict[str, Any] = {
        "index_version": INDEX_VERSION,
        "embedding_model": get_model_name(),
        "embedding_dimension": index.d,
        "chunk_count": len(chunks),
        "chunks": [chunk.model_dump() for chunk in chunks],
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def get_model_name() -> str:
    from app.core.config import get_settings

    return get_settings().embedding_model_name


def load_vector_store() -> tuple[faiss.IndexFlatIP, list[JobChunk]]:
    """Loads and validates the index + metadata, cached per file state (path, mtime,
    size) and configured embedding model (M4.3 Experiment 10). Every check below still
    runs whenever the files or the model setting change; a rebuilt index is picked up
    on the next call. `clear_vector_store_cache()` resets the cache."""
    if not INDEX_PATH.is_file() or not METADATA_PATH.is_file():
        raise VectorStoreError(
            f"Vector store is incomplete. Build it with scripts/build_job_vector_index.py: {VECTOR_STORE_DIRECTORY}"
        )
    index_stat, metadata_stat = INDEX_PATH.stat(), METADATA_PATH.stat()
    index, chunks = _load_and_validate_store(
        str(INDEX_PATH), str(METADATA_PATH), index_stat.st_mtime_ns, index_stat.st_size,
        metadata_stat.st_mtime_ns, metadata_stat.st_size, get_model_name(),
    )
    return index, list(chunks)


def clear_vector_store_cache() -> None:
    _load_and_validate_store.cache_clear()


@lru_cache(maxsize=2)
def _load_and_validate_store(index_path: str, metadata_path: str, *_file_state_and_model) -> tuple[faiss.IndexFlatIP, tuple[JobChunk, ...]]:
    try:
        index = faiss.read_index(index_path)
        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise VectorStoreError(f"Unable to load vector store: {exc}") from exc
    if metadata.get("index_version") != INDEX_VERSION:
        raise VectorStoreError("Unsupported vector store index version.")
    if metadata.get("embedding_model") != get_model_name():
        raise VectorStoreError("Vector store embedding model does not match configured model.")
    if metadata.get("embedding_dimension") != embedding_dimension() or index.d != embedding_dimension():
        raise VectorStoreError("Vector store embedding dimension is inconsistent.")
    chunks = [JobChunk.model_validate(chunk) for chunk in metadata.get("chunks", [])]
    if metadata.get("chunk_count") != len(chunks) or index.ntotal != len(chunks):
        raise VectorStoreError("Vector store vector and metadata counts are inconsistent.")
    return index, tuple(chunks)
