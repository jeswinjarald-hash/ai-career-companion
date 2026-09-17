import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.schemas.job_chunk import JobChunk
from app.services.embedding_service import embedding_dimension

VECTOR_STORE_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "vector_store"
INDEX_PATH = VECTOR_STORE_DIRECTORY / "internship_jobs.faiss"
METADATA_PATH = VECTOR_STORE_DIRECTORY / "internship_jobs_metadata.json"
INDEX_VERSION = "1.0"


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
    if not INDEX_PATH.is_file() or not METADATA_PATH.is_file():
        raise VectorStoreError(
            f"Vector store is incomplete. Build it with scripts/build_job_vector_index.py: {VECTOR_STORE_DIRECTORY}"
        )
    try:
        index = faiss.read_index(str(INDEX_PATH))
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
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
    return index, chunks
